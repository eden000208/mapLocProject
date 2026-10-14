"""旧模块兼容入口；业务实现统一位于 services/auth.py。"""

from .controllers.auth import router as router
from .dependencies import (
    current_user as current_user,
)
from .dependencies import (
    require_admin as require_admin,
)
from .dependencies import (
    require_query as require_query,
)
from .dto.auth import (
    LoginBody as LoginBody,
)
from .dto.auth import (
    PasswordBody as PasswordBody,
)
from .dto.auth import (
    UserBody as UserBody,
)
from .dto.auth import (
    UserPatch as UserPatch,
)
from .services.auth import (
    cell_visible as cell_visible,
)
from .services.auth import (
    change_password as change_password,
)
from .services.auth import (
    clean_scopes as clean_scopes,
)
from .services.auth import (
    create_user as create_user,
)
from .services.auth import (
    edit_user as edit_user,
)
from .services.auth import (
    hash_password as hash_password,
)
from .services.auth import (
    login as login,
)
from .services.auth import (
    logout as logout,
)
from .services.auth import (
    me as me,
)
from .services.auth import (
    scope_options as scope_options,
)
from .services.auth import (
    token_hash as token_hash,
)
from .services.auth import (
    user_payload as user_payload,
)
from .services.auth import (
    users as users,
)
from .services.auth import (
    verify_password as verify_password,
)
from .services.auth import (
    visible_filter as visible_filter,
)
