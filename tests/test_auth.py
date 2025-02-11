import json
from typing import Optional

import pytest
from httpx import AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin import (
    BaseAdmin,
    IntegerField,
    StringField,
    TinyMCEEditorField,
)
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed
from starlette_admin.views import CustomView

from tests.dummy_model_view import DummyBaseModel, DummyModelView

users = {
    "admin": ["admin"],
    "john": ["post:list", "post:detail"],
    "terry": ["post:list", "post:create", "post:edit"],
    "doe": [""],
}


class Post(DummyBaseModel):
    title: str
    content: str
    views: Optional[int] = 0


class ReportView(CustomView):
    def is_accessible(self, request: Request) -> bool:
        return "admin" in request.state.user_roles


@pytest.fixture()
def report_view() -> ReportView:
    return ReportView(
        "Report",
        icon="fa fa-report",
        path="/report",
        template_path="report.html",
        name="report",
    )


class PostView(DummyModelView):
    page_size = 2
    model = Post
    fields = (
        IntegerField("id"),
        StringField("title"),
        TinyMCEEditorField("content"),
        IntegerField("views"),
    )
    searchable_fields = ("title", "content")
    sortable_fields = ("id", "title", "content", "views")
    db = {}
    seq = 1

    def is_accessible(self, request: Request) -> bool:
        return (
            "admin" in request.state.user_roles
            or "post:list" in request.state.user_roles
        )

    def can_view_details(self, request: Request) -> bool:
        return "post:detail" in request.state.user_roles

    def can_create(self, request: Request) -> bool:
        return "post:create" in request.state.user_roles

    def can_edit(self, request: Request) -> bool:
        return "post:edit" in request.state.user_roles

    def can_delete(self, request: Request) -> bool:
        return "admin" in request.state.user_roles


class MyAuthProvider(AuthProvider):
    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
        response: Response,
    ) -> Response:
        if len(username) < 3:
            raise FormValidationError(
                {"username": "Ensure username has at least 03 characters"}
            )
        if username in users and password == "password":
            response.set_cookie(key="session", value=username)
            return response
        raise LoginFailed("Invalid username or password")

    async def is_authenticated(self, request) -> bool:
        if "session" in request.cookies:
            username = request.cookies.get("session")
            user_roles = users.get(username, None)
            if user_roles is not None:
                """Save user roles in request state, can be use later,
                to restrict user actions in admin interface"""
                request.state.user = username
                request.state.user_roles = user_roles
                return True
        return False

    def get_admin_user(self, request: Request) -> Optional[AdminUser]:
        return AdminUser(request.state.user)

    async def logout(self, request: Request, response: Response):
        response.delete_cookie("session")
        return response


class TestAuth:
    @pytest.mark.asyncio
    async def test_auth_route(self):
        admin = BaseAdmin(auth_provider=AuthProvider())
        app = Starlette()
        admin.mount_to(app)
        assert app.url_path_for("admin:login") == "/admin/login"
        assert app.url_path_for("admin:logout") == "/admin/logout"
        client = AsyncClient(app=app, base_url="http://testserver")
        response = await client.get("/admin/login")
        assert response.status_code == 200
        response = await client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert (
            response.headers.get("location")
            == "http://testserver/admin/login?next=http%3A%2F%2Ftestserver%2Fadmin%2F"
        )

    @pytest.mark.asyncio
    async def test_not_implemented_login(self):
        admin = BaseAdmin(auth_provider=AuthProvider())
        app = Starlette()
        admin.mount_to(app)
        client = AsyncClient(app=app, base_url="http://testserver")
        response = await client.post(
            "/admin/login",
            follow_redirects=False,
            data={"username": "admin", "password": "password", "remember_me": "on"},
        )
        assert "Not Implemented" in response.text

    @pytest.mark.asyncio
    async def test_custom_login_path(self):
        admin = BaseAdmin(auth_provider=MyAuthProvider(login_path="/custom-login"))
        app = Starlette()
        admin.mount_to(app)
        assert app.url_path_for("admin:login") == "/admin/custom-login"
        client = AsyncClient(app=app, base_url="http://testserver")
        response = await client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert (
            response.headers.get("location")
            == "http://testserver/admin/custom-login?next=http%3A%2F%2Ftestserver%2Fadmin%2F"
        )

    @pytest.mark.asyncio
    async def test_invalid_login(self):
        admin = BaseAdmin(auth_provider=MyAuthProvider())
        app = Starlette()
        admin.mount_to(app)
        assert app.url_path_for("admin:login") == "/admin/login"
        client = AsyncClient(app=app, base_url="http://testserver")
        data = {"username": "ad", "password": "invalid-password", "remember_me": "on"}
        response = await client.post("/admin/login", follow_redirects=False, data=data)
        assert "Ensure username has at least 03 characters" in response.text
        data["username"] = "admin"
        response = await client.post("/admin/login", follow_redirects=False, data=data)
        assert "Invalid username or password" in response.text

    @pytest.mark.asyncio
    async def test_valid_login(self):
        admin = BaseAdmin(auth_provider=MyAuthProvider())
        app = Starlette()
        admin.mount_to(app)
        assert app.url_path_for("admin:login") == "/admin/login"
        client = AsyncClient(app=app, base_url="http://testserver")
        response = await client.post(
            "/admin/login",
            data={"username": "admin", "password": "password", "remember_me": "on"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "http://testserver/admin/"
        assert "session" in response.cookies
        assert response.cookies.get("session") == "admin"
        response = await client.get(
            "/admin/logout", follow_redirects=False, cookies={"session": "admin"}
        )
        assert response.status_code == 303
        assert "session" not in response.cookies


class TestAccess:
    def setup_method(self, method):
        PostView.db.clear()
        with open("./tests/data/posts.json") as f:
            for post in json.load(f):
                del post["tags"]
                PostView.db[post["id"]] = Post(**post)
        PostView.seq = len(PostView.db.keys()) + 1

    @pytest.fixture
    def client(self, report_view):
        admin = BaseAdmin(
            auth_provider=MyAuthProvider(), templates_dir="tests/templates"
        )
        app = Starlette()
        admin.add_view(report_view)
        admin.add_view(PostView)
        admin.mount_to(app)
        return AsyncClient(app=app, base_url="http://testserver")

    @pytest.mark.asyncio
    async def test_access_custom_view(self, client: AsyncClient):
        response = await client.get("/admin/report", cookies={"session": "john"})
        assert response.status_code == 403
        response = await client.get("/admin/report", cookies={"session": "admin"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_access_model_view_list(self, client: AsyncClient):
        response = await client.get("/admin/post/list", cookies={"session": "doe"})
        assert response.status_code == 403
        response = await client.get("/admin/api/post", cookies={"session": "doe"})
        assert response.status_code == 403
        response = await client.get("/admin/post/list", cookies={"session": "john"})
        assert response.status_code == 200
        response = await client.get("/admin/api/post", cookies={"session": "john"})
        assert response.status_code == 200
        assert '<span class="nav-link-title">Report</span>' not in response.text

    @pytest.mark.asyncio
    async def test_access_model_view_detail(self, client: AsyncClient):
        response = await client.get("/admin/post/detail/1", cookies={"session": "john"})
        assert response.status_code == 200
        response = await client.get(
            "/admin/post/detail/1", cookies={"session": "terry"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_access_model_view_create(self, client: AsyncClient):
        response = await client.get("/admin/post/create", cookies={"session": "john"})
        assert response.status_code == 403
        response = await client.post("/admin/post/create", cookies={"session": "john"})
        assert response.status_code == 403
        response = await client.get("/admin/post/create", cookies={"session": "terry"})
        assert response.status_code == 200
        data = {"title": "title", "content": "content"}
        response = await client.post(
            "/admin/post/create",
            data=data,
            cookies={"session": "terry"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_access_model_view_edit(self, client: AsyncClient):
        response = await client.get("/admin/post/edit/1", cookies={"session": "john"})
        assert response.status_code == 403
        response = await client.post("/admin/post/edit/1", cookies={"session": "john"})
        assert response.status_code == 403
        response = await client.get("/admin/post/edit/1", cookies={"session": "terry"})
        assert response.status_code == 200
        response = await client.post(
            "/admin/post/edit/1", cookies={"session": "terry"}, follow_redirects=True
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_access_model_view_delete(self, client):
        response = await client.post(
            "/admin/api/post/action",
            params={"pks": [1, 2], "name": "delete"},
            cookies={"session": "john"},
        )
        assert response.status_code == 400
        response = await client.post(
            "/admin/api/post/action",
            params={"pks": [1, 2], "name": "delete"},
            cookies={"session": "doe"},
        )
        assert response.status_code == 400
        response = await client.post(
            "/admin/api/post/action",
            params={"pks": [1, 2], "name": "delete"},
            cookies={"session": "terry"},
        )
        assert response.status_code == 400
        response = await client.post(
            "/admin/api/post/action",
            params={"pks": [1, 2], "name": "delete"},
            cookies={"session": "admin"},
        )
        assert response.status_code == 200
