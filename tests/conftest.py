"""pytest 全局夹具。

D7-R2：``reject`` 会 best-effort 落 human-rejected 样例到 ``settings.FAILURES_ROOT``（默认
``BASE_DIR/prompts``）。为避免测试污染仓库 ``prompts/``，默认把落档根隔离到临时目录；
需要断言落档文件的用例可再覆盖 ``settings.FAILURES_ROOT``。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_failures_root(settings, tmp_path_factory):
    settings.FAILURES_ROOT = tmp_path_factory.mktemp("failures_root")