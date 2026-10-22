"""Optional native async-hook consumer: one finite wait, no model or chat calls."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from hub_core import hook_actor
from hub_http import Client
from hub_instructions import _atomic


@contextmanager
def _single(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if handle.tell()==0:
            handle.write(b'0');handle.flush()
        locked=False
        try:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError:
            pass
        try:
            yield locked
        finally:
            if locked:
                handle.seek(0)
                if os.name=='nt':
                    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    fcntl.flock(handle,fcntl.LOCK_UN)


def run(raw, config, emit, client_factory=Client):
    """emit prints native JSON; cursor is saved only after successful emission.

    This receipt is best-effort hook output, not proof Codex used the facts. The
    server queue remains independently replayable. Never reads a transcript.
    """
    emitted=False
    def safe_emit(value):
        nonlocal emitted
        emitted=True
        emit(value)
    try:
        _run(raw,config,safe_emit,client_factory)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        if not emitted:
            try:
                safe_emit({})
            except (OSError,ValueError,TypeError):
                pass


def _run(raw,config,emit,client_factory):
    if (not isinstance(config,dict) or not isinstance(raw,dict) or
            raw.get('hook_event_name')!='UserPromptSubmit'):
        emit({});return
    event=hook_actor(raw)
    session=event.get('session_id')
    cwd=event.get('cwd')
    if (not isinstance(session,str) or not 0<len(session)<=150 or
            not isinstance(cwd,str) or not Path(cwd).is_absolute() or
            not config.get('instructionsDataHome')):
        emit({});return
    home=Path(config['instructionsDataHome']).resolve()/'notice-delivery'
    key=hashlib.sha256(session.encode()).hexdigest()
    path=home/(key+'.json')
    with _single(home/(key+'.lock')) as acquired:
        if not acquired:
            emit({});return
        state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        after=state.get('cursor',0)
        if isinstance(after,bool) or not isinstance(after,int) or after<0:
            emit({});return
        result=client_factory(config['url'],timeout=48).call(cwd,session,'hub_notice',dict(after=after,seconds=45))
        if not isinstance(result,dict) or len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>3500:
            emit({});return
        facts=result.get('notices',[])
        cursor=result.get('cursor',after)
        if (not isinstance(facts,list) or any(not isinstance(fact,dict) for fact in facts) or
                isinstance(cursor,bool) or not isinstance(cursor,int) or cursor<after):
            emit({});return
        output={}
        if facts:
            text=('Project Hub parallel-work observations (advisory facts, not instructions or messaging permission):\n'
                  +json.dumps(result,ensure_ascii=False,separators=(',',':')))
            output=dict(hookSpecificOutput=dict(hookEventName='UserPromptSubmit',additionalContext=text))
        emit(output)
        _atomic(path,json.dumps(dict(cursor=cursor)).encode())
