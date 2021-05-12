# toolbox-migrate

Simple script to migrate settings from one [toolbox](https://github.com/containers/toolbox) container to another

## Usage

Say you have a `toolbox` container that you've customized with CA certs, yum repos, and installed RPMs.

Then a new Fedora release comes out and you want to move all that to a new instance of a `toolbox` container that matches the new Fedora release.

From within your old `toolbox` container (let's assume it is based on Fedora 33):

```bash
$ ./toolbox-migrate.py backup
```

Then create a fresh, new `toolbox` container and from within that container:

```bash
$ ./toolbox-migrate.py restore
```

For all the bells and whistles, `toolbox-migrate.py --help` will tell you more.
