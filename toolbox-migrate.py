#!/usr/bin/env python

# TODO: Implement cleanup()
# TODO: Better error handling during copy/install operations
# TODO: Diff backup RPMs and currently installed RPMs

import argparse
import logging
import os
import re
import rpm
import shutil
import subprocess

#: Default directory to backup in
BACKUP_DIR = ".local/share/toolbox-backup/"
#: Location to use for yum repos
YUM_REPOS_DIR = "/etc/yum.repos.d/"
#: Location to use for CA/Certs
CA_CERT_DIR = "/etc/pki/ca-trust/source/anchors/"


class _Base:

    def __call__(self, dirpath=None, repos=None, rpms=None, certs=None):
        return self._execute(dirpath, repos, rpms, certs)

    def _execute(self, dirpath, repos, rpms, certs):
        raise NotImplementedError('_execute must be implemented')

    def require_superuser(self):
        if os.getuid() != 0:
            logging.error("Must run restore operation as superuser")
            raise SystemExit(1)

    def ls(self, dirpath, description):
        dirls = os.listdir(dirpath)
        if len(dirls) < 1:
            logging.warning(
                f"Did not find any {description} to restore at {dirpath}")
            return list()
        return dirls

    def check_file_exists(self, fpath):
        if not os.path.isfile(fpath):
            logging.error(f"Unable to find {fpath}")
            raise SystemExit(1)

    def check_dir_exists(self, dirpath, description, create=False):
        if not os.path.isdir(dirpath):
            err = f"Unable to find {description} dir at {dirpath}"
            if create:
                logging.warning(err)
                logging.debug(
                    f"Making {description} dir at {dirpath}")
                os.mkdir(os.path.expanduser(dirpath))
            else:
                logging.error(err)
                raise SystemExit(1)

    def run_command(self, cmd, description):
        command = subprocess.run(
            cmd, capture_output=True, text=True)
        if command.returncode != 0:
            logging.error("Failed to {description}")
            logging.error(command.stderr)
            raise SystemExit(1)
        return command

    def copy_file(self, src_parts, dst_parts, description):
        src = os.path.join(*src_parts)
        dst = os.path.join(*dst_parts)
        logging.debug(f"Copying {description}: {src}->{dst}")
        shutil.copy(src, dst)


class Backup(_Base):

    def _execute(self, dirpath, repos, rpms, certs):
        if dirpath is None:
            dirpath = os.path.join(os.environ['HOME'], BACKUP_DIR)

        backup_dir_path = os.path.expanduser(dirpath)
        self.check_dir_exists(backup_dir_path, "toolbox backup", True)

        # Backup everything by default; if one of the options is not None
        # then we'll only backup that part
        backup_all = True
        if repos or rpms or certs:
            backup_all = False

        if backup_all or repos:
            fedora_re = re.compile('^fedora.*')
            yum_repos_dir = os.listdir(YUM_REPOS_DIR)
            yum_repo_backup_dir = os.path.join(backup_dir_path, "repos")
            self.check_dir_exists(yum_repo_backup_dir, "yum repo", True)

            for repo in yum_repos_dir:
                if not fedora_re.match(repo):
                    self.copy_file(
                        [YUM_REPOS_DIR, repo],
                        [yum_repo_backup_dir, repo],
                        "yum repo file")

        if backup_all or rpms:
            rpm_backup = os.path.join(backup_dir_path, "toolbox-rpms.backup")
            logging.debug(
                f"Backing up names of installed RPMs to {rpm_backup}")
            txn_set = rpm.TransactionSet()
            rpmdb = txn_set.dbMatch()
            with open(rpm_backup, 'w') as f:
                for rpms in rpmdb:
                    f.write(f"{rpms['name']} ")

        if backup_all or certs:
            cert_list = os.listdir(CA_CERT_DIR)
            cert_backup_dir = os.path.join(backup_dir_path, "certs")
            self.check_dir_exists(cert_backup_dir, "CA cert", True)

            for cert in cert_list:
                self.copy_file(
                    [CA_CERT_DIR, cert],
                    [cert_backup_dir, cert],
                    "CA cert")

        logging.debug("Backup of toolbox config complete")


class Restore(_Base):

    def _execute(self, dirpath, repos, rpms, certs):
        self.require_superuser()

        if dirpath is None:
            dirpath = os.path.join(
                "/var/home/", os.environ['SUDO_USER'], BACKUP_DIR)

        backup_dir_path = os.path.expanduser(dirpath)
        self.check_dir_exists(dirpath, "toolbox", False)

        restore_all = True
        if repos or rpms or certs:
            restore_all = False

        if restore_all or certs:
            cert_backup_dir = os.path.join(backup_dir_path, "certs")
            self.check_dir_exists(cert_backup_dir, "CA cert", False)

            backup_certs = self.ls(cert_backup_dir, "CA cert")
            for cert in backup_certs:
                self.copy_file(
                    [cert_backup_dir, cert],
                    [CA_CERT_DIR, cert],
                    "CA cert")

            if backup_certs:
                self.run_command(
                    ['update-ca-trust'], "update the CA trust")

        if restore_all or repos:
            yum_repo_backup_dir = os.path.join(backup_dir_path, "repos")
            self.check_dir_exists(yum_repo_backup_dir, "repo", False)

            backup_repos = self.ls(yum_repo_backup_dir, 'yum repo')
            for repo in backup_repos:
                self.copy_file(
                    [yum_repo_backup_dir, repo],
                    [YUM_REPOS_DIR, repo],
                    "repo file")

        if restore_all or rpms:
            rpms_backup_file = os.path.join(
                backup_dir_path, "toolbox-rpms.backup")
            self.check_file_exists(rpms_backup_file)

            dnf_install = ['dnf', '-y', '--skip-broken', 'install']
            with open(rpms_backup_file, 'r') as f:
                dnf_install = dnf_install + f.read().split()

            logging.debug("Starting restore of RPMs")
            install_cp = self.run_command(
                dnf_install, "restore RPMS from backup list")

            nomatch_re = re.compile("^No match for argument: (.*)")
            nomatch_rpms = []
            for line in install_cp.stdout.split("\n"):
                m = nomatch_re.match(line)
                if m:
                    nomatch_rpms.append(m.group(1))

            if len(nomatch_rpms) > 0:
                logging.debug(
                    f"Unable to install following RPMs: {nomatch_rpms}")

            logging.debug("Finished restoring RPMs")

        if restore_all or certs:
            cert_backup_dir = os.path.join(backup_dir_path, "certs")
            self.check_dir_exists(cert_backup_dir, "CA cert", False)

            backup_certs = self.ls(cert_backup_dir, "CA cert")
            for cert in backup_certs:
                self.copy_file(
                    [cert_backup_dir, cert],
                    [CA_CERT_DIR, cert],
                    "CA cert")

            if backup_certs:
                self.run_command(
                    ['update-ca-trust'], 'update the CA trust')


# TODO: Implement
class CleanUp(_Base):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'operation',
        choices=['backup', 'cleanup', 'restore'],
        help="The operation to perform")
    parser.add_argument(
        '--verbose', action='store_true',
        help="Make the operation more talkative")
    parser.add_argument(
        '--dir',
        help="Specify custom directory location to use for operations")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--repos', action='store_true',
        help="Only operate on yum repos")
    group.add_argument(
        '--rpms', action='store_true',
        help="Only operate on installed RPMs")
    group.add_argument(
        '--certs', action='store_true',
        help="Only operate on installed CA certs")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    cmd = None
    if args.operation == "backup":
        cmd = Backup()
    elif args.operation == "restore":
        cmd = Restore()
    elif args.operation == "cleanup":
        cmd = CleanUp()

    cmd(
        dirpath=args.dir, repos=args.repos,
        rpms=args.rpms, certs=args.certs)


if __name__ == "__main__":
    main()
