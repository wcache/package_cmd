from pathlib import PurePath
from urllib.parse import urlparse
from git import Submodule, Repo
from git.exc import GitError


class UnBoundError(GitError):
    pass


class RepoTypeError(GitError):
    pass


class RemoteDoesNotExists(GitError):
    pass


class SubmoduleNotFound(GitError):
    pass


class Repository(object):
    submodule_prefix = 'components'

    def __init__(self, repo):
        if not isinstance(repo, Repo):
            raise RepoTypeError('repo must be a <git.Repo> object')

        self.__repo__ = repo
        self.name = PurePath(self.__repo__.working_dir).stem

    def __str__(self):
        if self.repo is None:
            raise UnBoundError(f'{self.__class__.__name__}(\"unbounded\")')
        return f'{self.__class__.__name__}(\"{self.git_dir}\")'

    def __repr__(self):
        return self.__str__()

    def __getattr__(self, item):
        attr = getattr(self.repo, item, None)
        if attr is None:
            raise AttributeError(f'{self.__class__} object has not attribute \'{item}\'')
        return attr

    @property
    def repo(self):
        repo = getattr(self, '__repo__', None)
        if repo is None:
            raise UnBoundError(f'{self.__class__.__name__}(\"unbounded\")')
        return repo

    @property
    def origin(self):
        try:
            return self.remote(name='origin')
        except ValueError:
            raise RemoteDoesNotExists('remote \"origin\" does not exists!')

    @property
    def commits(self):
        return [c.hexsha for c in self.iter_commits()]

    @classmethod
    def clone(cls, url, to_path):
        repo = Repo.clone_from(url, to_path)
        return cls(repo)

    @classmethod
    def load(cls, path='.'):
        repo = Repo(path)
        return cls(repo)

    @classmethod
    def new(cls, path='.'):
        repo = Repo.init(path)
        return cls(repo)

    def status(self, simple=True):
        args = []
        if simple:
            args.append('-s')
        return self.git.status(*args)

    def add_submodule(self, url, branch):
        result = urlparse(url)
        submodule_name = PurePath(result.path).stem
        save_path = str(self.submodule_prefix / PurePath(submodule_name))
        return Submodule.add(
            self.repo,
            submodule_name,
            save_path,
            url,
            branch,
        )

    def remove_submodule(self, submodule_name):
        try:
            self.submodules[submodule_name].remove()
        except IndexError:
            raise SubmoduleNotFound(f'{submodule_name} not found.')

    def update_submodule(self):
        for sub in self.submodules:
            sub.update(recursive=True)

    def add(self, files=()):
        self.git.add(files or '.')

    def commit(self, author='', message=''):
        args = []
        if message:
            args.extend(('-m', message))
        if author:
            args.extend(('a', author))
        self.git.commit(*args)

    def push(self, **options):
        """git push origin"""
        # 先推送submodule的更新,然后推送主项目的更新(如果submodule推送失败,那么推送任务直接终止)
        options.setdefault('recurse_submodules', 'on-demand')
        self.origin.push(**options)

    def pull(self, **options):
        """git pull origin"""
        # 拉取所有子仓库(fetch)并merge到所跟踪的分支上
        options.setdefault('recurse_submodules', True)
        self.origin.pull(**options)
        self.make_head_no_detached()

    def make_head_no_detached(self):
        """把当前所有子仓库的HEAD从游离状态中恢复到跟踪分支(依赖状态保持同步)。
        逻辑如下：
            # 1、获取与当前主仓库依赖的提交id
            # 2、子仓库切换到依赖的跟踪分支(git checkout <跟踪分支>)
            # 3、根据依赖的提交id,重置当前分支到指定提交(git reset --hard <依赖的提交id>)
        """
        for sub in self.submodules:
            commit_id = sub.hexsha
            repo = Repository(sub.module())
            repo.git.checkout(sub.branch.name)
            repo.git.reset('--hard', commit_id)

    def checkout(self, index, **options):
        # 切换子仓库，同时让子模块处于正确的状态
        options.setdefault('recurse_submodules', True)
        self.git.checkout(index, **options)
        self.make_head_no_detached()
