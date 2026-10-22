"""Read legacy and additive work links without duplicating work boundaries."""
PHASES = ('planning', 'research', 'implementation', 'review', 'testing')
WAITING_KINDS = ('external_dependency', 'user_confirmation')


def stages_for(connection, work):
    primary = connection.execute('SELECT stage FROM work_stages WHERE work=?', (work,)).fetchone()
    result = [primary[0]] if primary else []
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_stage_links'").fetchone():
        result.extend(row[0] for row in connection.execute(
            'SELECT stage FROM work_stage_links WHERE work=? ORDER BY stage', (work,)) if row[0] not in result)
    return result


def describe(connection, item):
    item['stages'] = stages_for(connection, item['id'])
    item['stage'] = item['stages'][0] if item['stages'] else None
    columns = {row[1] for row in connection.execute('PRAGMA table_info(work)')}
    if 'phase' in columns:
        waiting = 'waiting_kind' if 'waiting_kind' in columns else 'NULL'
        row = connection.execute('SELECT phase,'+waiting+' FROM work WHERE id=?', (item['id'],)).fetchone()
        if row:
            item.update(phase=row[0], waitingKind=row[1])
    else:
        item.update(phase='legacy', waitingKind=None)
    return item
