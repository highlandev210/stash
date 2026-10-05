import typer


def install_commands(app, main):
    watcher = typer.Typer(no_args_is_help=True)
    app.add_typer(watcher, name='watcher')

    @watcher.command('enable')
    def enable(): main.emit(main.request('PUT', main.base()+'/watcher', {'enabled': True, 'actor': main.state['actor']}))

    @watcher.command('disable')
    def disable(): main.emit(main.request('PUT', main.base()+'/watcher', {'enabled': False, 'actor': main.state['actor']}))

    @watcher.command('status')
    def status(): main.emit(main.request('GET', main.base()+'/watcher'))

    @watcher.command('observations')
    def observations(): main.emit(main.request('GET', main.base()+'/file-observations'))
