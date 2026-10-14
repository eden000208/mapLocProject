"""旧模块兼容入口；业务实现统一位于 services/stations.py。"""

from .controllers.stations import router as router
from .dto.stations import (
    PreviewBody as PreviewBody,
)
from .dto.stations import (
    SelectionBody as SelectionBody,
)
from .dto.stations import (
    StationPatch as StationPatch,
)
from .services.stations import (
    _visible as _visible,
)
from .services.stations import (
    admin_stations as admin_stations,
)
from .services.stations import (
    cell_payload as cell_payload,
)
from .services.stations import (
    confirm as confirm,
)
from .services.stations import (
    csv_response as csv_response,
)
from .services.stations import (
    edit_station as edit_station,
)
from .services.stations import (
    errors_csv as errors_csv,
)
from .services.stations import (
    get_index as get_index,
)
from .services.stations import (
    invalidate_index as invalidate_index,
)
from .services.stations import (
    map_stations as map_stations,
)
from .services.stations import (
    own_batch as own_batch,
)
from .services.stations import (
    parse_integer as parse_integer,
)
from .services.stations import (
    parse_rows as parse_rows,
)
from .services.stations import (
    preview as preview,
)
from .services.stations import (
    read_upload as read_upload,
)
from .services.stations import (
    resolve as resolve,
)
from .services.stations import (
    template as template,
)
from .services.stations import (
    upload as upload,
)
from .services.stations import (
    validate_cells as validate_cells,
)
