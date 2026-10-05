from pathlib import Path
from typing import Optional
import json
import typer
from stash.codex_runtime import Runtime, find_root, status


def install_commands(app,main):
    integrations=typer.Typer(no_args_is_help=True)
    codex=typer.Typer(no_args_is_help=True)
    integrations.add_typer(codex,name='codex');app.add_typer(integrations,name='integrations')

    @codex.command('install')
    def install(path: Path=Path('.'),no_skill: bool=False):
        from .codex_install import install
        try: value=install(path,main.state['server'].removesuffix('/api/v1'),not no_skill)
        except ValueError as error:
            main.fail('installation_failed',str(error),2)
        except Exception:
            main.fail('installation_failed','Could not install safely. Existing custom skills/hooks are preserved; inspect project permissions and configuration. No trust was bypassed.',2)
        main.emit(value)

    @codex.command('uninstall')
    def uninstall(path: Path=Path('.')):
        from .codex_install import uninstall
        try: value=uninstall(path)
        except Exception: main.fail('installation_failed','Could not remove hooks safely; inspect project permissions',2)
        main.emit(value)

    @codex.command('status')
    def current(path: Optional[Path]=None):
        try: value=status(path.resolve() if path else find_root(Path.cwd()))
        except Exception: main.fail('unresolved_project','Cannot read integration status in this project',3)
        main.emit(value)

    @codex.command('drain')
    def drain(path: Optional[Path]=None):
        from stash.codex_worker import drain
        try: result=drain(path.resolve() if path else find_root(Path.cwd()))
        except Exception: main.fail('invalid_queue','Queue could not be read safely; retain it and inspect configuration',2)
        main.emit(result)
        if result['error']: raise typer.Exit(1)

    @codex.command('bind')
    def bind(runtime_key: str,session: str=typer.Option(...,'--session')):
        from stash.store import valid_id
        try:
            if len(runtime_key)!=64 or any(c not in '0123456789abcdef' for c in runtime_key): raise ValueError()
            valid_id(session)
        except Exception: main.fail('invalid_input','Provide the runtime key from SessionStart and a canonical session UUID',2)
        # Verify project/session before changing the local mapping. Queued events retain their original binding.
        main.request('GET',main.base()+f'/sessions/{session}')
        root=find_root(Path.cwd())
        with Runtime(root) as runtime:
            config=runtime.config()
            if not config or config['project_id']!=main.project_id(): main.fail('conflict','Integration and selected project differ',4)
            runtime.write(f'runtime/codex/bindings/{runtime_key}.json',{'runtime_key':runtime_key,'session_id':session})
        main.emit({'runtime_key':runtime_key,'session_id':session})

    @codex.command('observations')
    def observations(): main.emit(main.request('GET',main.base()+'/observations'))
