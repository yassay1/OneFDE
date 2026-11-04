from onefde.modules.tasks import models as m


def task_event(db, task, kind, actor, summary, **data):
    task.event_sequence += 1
    db.add(
        m.TaskEvent(
            task_id=task.id,
            sequence=task.event_sequence,
            kind=kind,
            actor=actor,
            summary=summary,
            data=data,
        )
    )


def run_event(db, run, kind, summary, **data):
    run.event_sequence += 1
    db.add(
        m.RunEvent(
            run_id=run.id,
            sequence=run.event_sequence,
            kind=kind,
            summary=summary,
            data=data,
        )
    )
