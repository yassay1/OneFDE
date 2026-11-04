from onefde.core.errors import ApiException

ACTIVE = ("queued", "running", "cancel_requested", "interrupted")
CLOSED = ("succeeded", "cancelled")


def conflict(code, message):
    raise ApiException(409, code, message)


def open_task(task):
    if task.state in CLOSED:
        conflict("TASK_CLOSED", "任务已关闭，后续工作请创建关联任务")


def no_active(task):
    if task.active_run_id:
        conflict("RUN_NOT_STOPPED", "当前运行尚未确认停止")


def no_pending(task):
    if task.pending_input_count:
        conflict("INPUTS_PENDING", "请先处理待采用输入和未答问题")


def validate_spec(spec):
    if spec.dependencies:
        conflict("DEPENDENCIES_NOT_SUPPORTED", "当前切片尚不支持非空任务依赖")
