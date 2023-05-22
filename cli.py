import os
import stat
import click
import requests
import shutil
from pathlib import Path
from texttable import Texttable
from git.exc import GitError
from core import Repository


# Application version
__VERSION__ = 'V1.0.0'
# GitHub API Info
USER = 'quecPy'
GITHUB_API_URL = 'https://api.github.com'
BASE_URL = 'https://github.com'
API_TOKEN = "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"

# GIT REPO INFO
PUBLIC_REPO_SOURCES = ['github.com', 'gitee.com']


def remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_remote_repos():
    """get repos list by orgs (order)"""
    rv = []
    url = GITHUB_API_URL + "/orgs/" + USER + "/repos"
    response = requests.get(
        url,
        headers={'Authorization': 'token %s' % API_TOKEN}
    )
    for repo in response.json():
        rv.append({
            "name": repo.get("name"),
            "url": repo.get("html_url")
        })
    return rv


@click.group()
@click.version_option(version=__VERSION__)
def cli():
    """package tool for QuecPython"""
    pass


@cli.command()
def git():
    """show the current git server."""
    click.secho(PUBLIC_REPO_SOURCES, fg="red")


@cli.command('import')
@click.argument('package', required=False)
@click.argument('to_path', required=False)
def import_(package, to_path):
    """
    import package from repository by name or url.

    @PACKAGE: package name or url.
    @TO_PATH: package path to save.
    """
    if package is None:
        remote_repos = get_remote_repos()
        tb = Texttable()
        tb.header(['name', 'url'])
        rows = []
        for repo in remote_repos:
            rows.append((repo['name'], repo['url']))
        tb.add_rows(rows, header=False)
        click.secho(tb.draw(), fg='cyan')
        return

    url = None
    if package.endswith('.git'):
        url = package
        to_path = to_path or Path(package).stem
    else:
        remote_repos = get_remote_repos()
        for repo in remote_repos:
            if repo['name'] == package:
                url = repo['url']
                to_path = to_path or package
                break

    if url is None:
        click.secho(f'can not found the url for {package}')
        return

    try:
        local_repo = Repository.clone(url, to_path)
        local_repo.update_submodule()
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(
            f'import error:\n'
            f'{tb.draw()}',
            fg='red'
        )


@cli.command('info')
def info():
    """show the local repository information."""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return

    tb = Texttable()
    tb.header(['name', 'branch', 'version', 'url'])
    tb.add_rows(
        [
            (
                local_repo.name,
                local_repo.active_branch,
                local_repo.tags[-1] if local_repo.tags else '@latest',
                local_repo.remotes[0].url if local_repo.remotes else 'N/A'  # 默认取第一个关联远程仓库url
            )
        ],
        header=False
    )
    click.secho(tb.draw(), fg='cyan')


def show_dependencies(local_repo):
    rows = []
    for submodule in local_repo.submodules:
        rows.append(
            (
                submodule.name,
                submodule.hexsha[:7],
                submodule.url
            )
        )
    if not rows:
        # click.secho(f'can not find any submodule in current repository \"{local_repo.name}\"')
        return

    tb = Texttable()
    tb.header(['name', 'commit-id', 'url'])
    tb.add_rows(rows, header=False)

    click.secho(f"{local_repo.name}\'s submodules:", fg='black')
    click.secho(tb.draw(), fg='cyan')

    for submodule in local_repo.submodules:
        show_dependencies(Repository(submodule.module()))


@cli.command('ls')
def ls():
    """list the local repository's dependencies."""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    show_dependencies(local_repo)


@cli.command('new')
@click.argument('name', required=False)
def new(name):
    """
    create a new repository according to NAME.

    \b
    if you don't pass NAME, the repository will be created in current working dir.
    if you pass NAME, the NAME should be a pathlike string which the repository placed in.

    @NAME: name or path of repository.
    """
    local_repo_git_path = Path('.git')
    if name is None and local_repo_git_path.exists():
        if click.confirm(f'a repository ALREADY EXISTS in current dir, '
                         f'we will REMOVE it and to initialize a new one. '
                         f'would you want to continue?'):
            shutil.rmtree(str(local_repo_git_path), onerror=remove_readonly)
            click.secho(f'remove \"{str(local_repo_git_path)}\".')
        else:
            click.secho('abort!')
            return

    path = name or '.'
    try:
        Repository.new(path)
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(f'init repository failed. details:\n{tb.draw()}', fg='red')
    else:
        click.secho(f'init repository successfully. repository dir: {path}', fg='green')


@cli.command('remove')
@click.argument('submodule', required=True)
def remove(submodule):
    """
    remove submodule.

    \b
    @SUBMODULE: name for submodule to remove.
    """
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    try:
        local_repo.remove_submodule(submodule)
    except GitError as e:
        click.secho(f'remove submodule error: {str(e)}', fg='red')
    else:
        click.secho(f'remove submodule successfully.', fg='green')


@cli.command('add')
@click.option('-b', '--branch', default='master', help='submodule\'s branch for tracking. default is \"master\"')
@click.argument('url', required=True)
def add(url, branch):
    """
    add submodule from remote repository.

    @URL: remote submodule url.
    """
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    try:
        local_repo.add_submodule(url, branch)
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(f'add submodule error: \n{tb.draw()}', fg='red')
    else:
        click.secho('add submodule successfully!', fg='green')


status_map = {
    ' ': 'Unmodified',
    'M': 'Modified',
    'T': 'file type changed',
    'A': 'Added',
    'D': 'Deleted',
    'R': 'Renamed',
    'C': 'Copied',
    'U': 'Updated but unmerged',
    '?': 'Untracked'
}


def show_status(repo):
    output = repo.status()
    if output:
        click.secho(f'{repo.name}\'s status:', fg='red')

        tb = Texttable()
        tb.header(['index', 'working tree', 'path'])
        tb.add_rows(
            [
                (
                    status_map.get(line[0].upper(), 'N/A'),
                    status_map.get(line[1].upper(), 'N/A'),
                    line[3:]
                )
                for line in output.splitlines()
            ],
            header=False
        )
        click.secho(f'{tb.draw()}', fg='cyan')
    else:
        click.secho(f'working tree is clean: \"{Path(repo.working_dir).relative_to(Path.cwd())}\"')

    for sub in repo.submodules:
        temp_repo = Repository(sub.module())
        show_status(temp_repo)


@cli.command('status')
def status():
    """view the status of the local code repository."""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    show_status(local_repo)


@cli.command('releases')
def releases():
    """check tags."""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    if local_repo.tags:
        tb = Texttable()
        tb.header(['name', 'commit-id'])
        rows = []
        for tag in local_repo.tags:
            rows.append([tag.name, tag.commit.hexsha])
        tb.add_rows(rows, header=False)
        click.secho(f'{tb.draw()}', fg='green')
    else:
        click.secho(f"no releases for {local_repo}.", fg='black')


@cli.command('publish')
def publish():
    """submit the code to the local repository."""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    try:
        local_repo.push()
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(f'push err:\n{tb.draw()}', fg='red')


@cli.command('update')
@click.option('-i', '--index', 'index', default='master', help='branch name | tag | commit-id for checkout.')
def update(index):
    """update local repository, auto update submodules recursively."""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    try:
        local_repo.checkout(index)
        # local_repo.pull()
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(f'failed to update {local_repo}. details:\n{tb.draw()}')
    else:
        click.secho(f'update {local_repo} successfully.')


@cli.command('sync')
def sync():
    """同步应用对组件的依赖关系"""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    click.secho('Components those are modified:')
    flag = False
    for sub in local_repo.submodules:
        sub_repo = Repository(sub.module())
        hs_list = [hs for hs in sub_repo.commits]
        index = hs_list.index(sub.hexsha)
        if index == 0:
            click.secho(f'{sub.name} (uncommitted): {sub.hexsha}')
        else:
            flag = True
            click.secho(f'{sub.name} (new commits): {sub.hexsha}, {index} versions behind the latest version')

    if flag:
        if not click.confirm(f'Some modified components are not committed, '
                             f'only committed ones can be synchronised, continue?'):
            click.secho('Abort!')
            return
    else:
        click.secho(f'All modified components are committed, synchronising...')

    try:
        local_repo.add(local_repo.submodule_prefix)
        local_repo.commit(message='auto sync submodules.')
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(f'sync err:\n{tb.draw()}')


@cli.command('deploy')
def deploy():
    """云端同步仓库的依赖关系"""
    try:
        local_repo = Repository.load()
    except GitError as e:
        click.secho(f'failed to load repository in current dir.', fg='red')
        click.secho('Abort!', fg='red')
        return None

    try:
        local_repo.pull()
    except GitError as e:
        tb = Texttable()
        tb.add_row([str(e)])
        click.secho(f'when deploy {local_repo}, error happened! here is details:')
        click.secho(f'{tb.draw()}')
    else:
        click.secho(f'deploy {local_repo} successfully.')


if __name__ == '__main__':
    cli()
