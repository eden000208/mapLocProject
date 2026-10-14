"""旧模块兼容入口；业务实现统一位于 services/detail_upload.py。"""

from .controllers.detail_upload import router as router
from .services.detail_upload import (
    clean_expired as clean_expired,
)
from .services.detail_upload import (
    confirm as confirm,
)
from .services.detail_upload import (
    csv_encoding as csv_encoding,
)
from .services.detail_upload import (
    existing_months as existing_months,
)
from .services.detail_upload import (
    file_rows as file_rows,
)
from .services.detail_upload import (
    iter_details as iter_details,
)
from .services.detail_upload import (
    own_batch as own_batch,
)
from .services.detail_upload import (
    preview as preview,
)
from .services.detail_upload import (
    scan_file as scan_file,
)
from .services.detail_upload import (
    target_table as target_table,
)
from .services.detail_upload import (
    upload as upload,
)
from .services.detail_upload import (
    validate_row as validate_row,
)
from .services.detail_upload import (
    write_batch as write_batch,
)
