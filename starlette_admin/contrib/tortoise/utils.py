import starlette_admin.fields as fields
from tortoise import fields as tfields
from tortoise.fields.relational import (
    ForeignKeyFieldInstance,
    ManyToManyFieldInstance,
    OneToOneFieldInstance,
)

from . import types as t

tortoise2starlette_admin_fields = {
    tfields.IntField: fields.IntegerField,
    tfields.BigIntField: fields.IntegerField,
    tfields.SmallIntField: fields.IntegerField,
    tfields.IntEnumField: fields.IntEnum,
    tfields.CharField: fields.StringField,
    tfields.CharEnumField: fields.EnumField,
    tfields.BooleanField: fields.BooleanField,
    tfields.DateField: fields.DateField,
    tfields.DatetimeField: fields.DateTimeField,
    tfields.FloatField: fields.FloatField,
    tfields.DecimalField: fields.DecimalField,
    tfields.UUIDField: fields.StringField,
    ForeignKeyFieldInstance: fields.HasOne,
    OneToOneFieldInstance: fields.HasOne,
    ManyToManyFieldInstance: fields.HasMany,
    tfields.TextField: fields.TinyMCEEditorField,
    tfields.TimeField: fields.TimeField,
}


def starlette_admin_order_by2tortoise_order_by(order_bys: t.OrderBy):
    def convert(order_by: str):
        field_part, order_part = order_by.split(" ")
        order_part = "" if order_by == "acs" else "-"
        return f"{order_part}{field_part}"

    return tuple(map(convert, order_bys))


def remove_nones(item: dict):
    return {
        k: remove_nones(v) if isinstance(v, dict) else v
        for k, v in item.items()
        if v is not None
    }


def add_id2fk_fields(data: dict, fields: t.Sequence[str]):
    fk_fields_ = set(fields)
    convert = lambda k: k if k not in fk_fields_ else f"{k}_id"
    return {convert(k): v for k, v in data.items()}


def identity(model_name: str, app_name=None):
    app_name = f"{app_name}_" if app_name else ""
    return f"{app_name}{model_name.split('.')[-1].lower()}"


def related_starlette_field(field_map_item: tuple, **kw):
    name, field = field_map_item
    starlette_type = tortoise2starlette_admin_fields[type(field)]
    kwargs = {"name": name, "label": name, "required": field.required}
    field_type = type(field)
    if field_type is ForeignKeyFieldInstance:
        kwargs.update(
            {"identity": identity(field.model_name, kwargs.get("_app_name_"))}
        )
    elif field_type is tfields.CharField:
        kwargs.update({"maxlength": field.max_length})
    elif field_type is tfields.DatetimeField:
        kwargs.update(
            {
                "required": field.required
                and not field.auto_now_add
                and not field.auto_now
            }
        )
    kwargs.update(kw)
    return starlette_type(**kwargs)


def tortoise_fields2starlette_fields(model: t.TortoiseModel, **kwargs):
    return tuple(
        related_starlette_field(i, **kwargs.get(i[0], {}))
        for i in model._meta.fields_map.items()
    )
