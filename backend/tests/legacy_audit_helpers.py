"""Frozen SQL fixture for pre-role schemas; independent of current ORM/services."""

from uuid import uuid4

from sqlalchemy import text


async def seed_legacy_audit(connection, *, include_security_events=True):
    ids = {
        name: uuid4()
        for name in (
            "user",
            "org",
            "project",
            "status",
            "task",
            "history",
            "event",
            "request",
            "task2",
            "link",
        )
    }
    statements = (
        "INSERT INTO users(id,email,password_hash,is_active,created_at,updated_at) "
        "VALUES (:user,'legacy@example.com','synthetic-unused',true,now(),now())",
        "INSERT INTO user_profiles(user_id,first_name,last_name,created_at,updated_at) "
        "VALUES (:user,'Legacy','User',now(),now())",
        "INSERT INTO organizations(id,owner_id,name) VALUES (:org,:user,'Legacy')",
        "INSERT INTO organization_members(organization_id,user_id) VALUES (:org,:user)",
        "INSERT INTO projects(id,organization_id,owner_id,name) VALUES (:project,"
        ":org,:user,'Legacy')",
        "INSERT INTO project_members(project_id,user_id) VALUES (:project,:user)",
        "INSERT INTO project_statuses(id,project_id,name,position,is_active,is_completed) "
        "VALUES (:status,:project,'Finished',0,true,true)",
        "INSERT INTO tasks(id,project_id,status_id,title,created_by,reporter_id,slug,"
        "sequence_number,created_at,updated_at) "
        "VALUES (:task,:project,:status,'Preserved',:user,:user,'LEG-1',1,now(),now())",
        "INSERT INTO task_history(id,task_id,changed_by,event_type,field_name,"
        "old_value,new_value,created_at) "
        "VALUES (:history,:task,:user,'title_changed','title','Before','Preserved',now())",
        "INSERT INTO security_events(id,event_type,actor_kind,actor_id,target_type,"
        "target_id,organization_id,request_id,created_at,details) "
        "VALUES (:event,'membership_added','user',:user,'organization',:org,:org,"
        ":request,now(),'{}')",
    )
    for statement in statements:
        if not include_security_events and statement.startswith("INSERT INTO security_events"):
            continue
        await connection.execute(text(statement), ids)
    await connection.execute(
        text(
            "INSERT INTO tasks(id,project_id,status_id,title,created_by,reporter_id,slug,"
            "sequence_number,created_at,updated_at) VALUES "
            "(:task2,:project,:status,'Linked',:user,:user,'LEG-2',2,now(),now())"
        ),
        ids,
    )
    task_a, task_b = sorted((ids["task"], ids["task2"]))
    await connection.execute(
        text(
            "INSERT INTO task_links(id,task_a_id,task_b_id,relation_type,created_by,created_at) "
            "VALUES (:link,:a,:b,'related',:user,now())"
        ),
        {**ids, "a": task_a, "b": task_b},
    )
    return ids
