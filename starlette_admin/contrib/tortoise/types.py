from typing import *
from tortoise.models import Model as _TModel

Where = Optional[Union[Dict[str, Any], str]]
OrderBy = Optional[List[str]]
Pk = int
Pks = Sequence[Pk]
TortoiseModel = _TModel
