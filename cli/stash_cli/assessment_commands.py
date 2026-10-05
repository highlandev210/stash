from pathlib import Path
from typing import Optional
import typer


def install_commands(app, main):
    assessments = typer.Typer(no_args_is_help=True)
    app.add_typer(assessments, name='assessments')

    @assessments.command('run')
    def run(goal: str = '', mode: str = 'existing', file: Optional[str] = None):
        """Inspect an existing/new project and save reviewable context and issue proposals."""
        payload = main.load_payload(file) if file else {'goal': goal, 'mode': mode}
        main.emit(main.request('POST', main.base() + '/assessments', {**payload, 'actor': main.state['actor']}))

    @assessments.command('list')
    def history():
        main.emit(main.request('GET', main.base() + '/assessments'))

    @assessments.command('refine')
    def refine(assessment_id: str, file: str = typer.Option(..., '--file')):
        """Submit evidence-backed semantic analysis with the original draft revision."""
        main.emit(main.request('PUT', main.base() + f'/assessments/{assessment_id}', {**main.load_payload(file), 'actor': main.state['actor']}))

    @assessments.command('approve')
    def approve(assessment_id: str, file: str = typer.Option(..., '--file')):
        """Apply selected context/issues and establish tracking with the original draft revision."""
        main.emit(main.request('POST', main.base() + f'/assessments/{assessment_id}/approve', {**main.load_payload(file), 'actor': main.state['actor']}))

    @main.projects.command('create')
    def create(path: Path):
        """Create an empty project folder inside an existing parent and register it."""
        main.emit(main.request('POST', '/projects/create', {'path': str(path.expanduser().absolute()), 'actor': main.state['actor']}))
