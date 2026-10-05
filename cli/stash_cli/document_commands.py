from pathlib import Path
from typing import Optional
import sys
import typer


def install_commands(app,main):
    docs=typer.Typer(no_args_is_help=True);app.add_typer(docs,name='docs')

    @docs.command('read')
    def read(path: str): main.emit(main.request('GET',main.base()+'/document',params={'path':path}))

    @docs.command('write')
    def write(path: str,file: str=typer.Option(...,'--file'),revision: Optional[str]=None,create: bool=False):
        if (create and revision is not None) or (not create and not revision):
            main.fail('invalid_input','Use --create for a missing document, or --revision with the original content hash',2)
        try: content=sys.stdin.read() if file=='-' else Path(file).read_text()
        except (OSError,UnicodeError): main.fail('invalid_input','Provide a readable Markdown file or stdin',2)
        main.emit(main.request('PUT',main.base()+'/document',{'path':path,'content':content,'revision':revision,'actor':main.state['actor']}))
