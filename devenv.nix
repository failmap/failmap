{ pkgs, inputs, ... }:

let
  python = pkgs.python310;
  pkgs-nuclei = import inputs.nixpkgs-nuclei { system = pkgs.stdenv.system; };
in
{
  packages = [
    # development requirements
    pkgs.git
    pkgs.gnumake

    # Python version to use (see above)
    python

    # required for building MySQL Python package
    pkgs.libmysqlclient.dev
    pkgs.postgresql

    # required for running dev environment
    pkgs.redis
    pkgs.nmap

    # additional tools
    pkgs.shellcheck

    # scanner dependencies
    pkgs.nuclei
    pkgs.nuclei-templates
  ];

  env.DEBUG = 1;
  env.NETWORK_SUPPORTS_IPV6 = 1;
  env.PIP_DISABLE_PIP_VERSION_CHECK = 1;
  env.DJANGO_SETTINGS_MODULE = "websecmap.settings";
  env.MYSQLCLIENT_CFLAGS = "-I${pkgs.libmysqlclient.dev}/include/mysql";
  env.MYSQLCLIENT_LDFLAGS = "-L${pkgs.libmysqlclient.dev}/lib";
  env.NUCLEI_BIN = "${pkgs-nuclei.nuclei}/bin/nuclei";
  env.PROJECT_WEBSITE = "http://localhost:8000";

  enterShell = ''
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib/
    python_version=$(python --version)
    echo $python_version

    # find a suitable place to create virtual environment outside of project directory
    if test "$(uname -s)" = "Darwin";then
        export VIRTUAL_ENV=~/Library/Caches/virtualenvs/$(basename $PWD)-''${python_version/\ /_}
    else
        export VIRTUAL_ENV=$\{XDG_CACHE_HOME:-~/.cache\}/virtualenvs/$(basename $PWD)-''${python_version/\ /_}
    fi
    echo "Virtualenv: $VIRTUAL_ENV"

    export PATH=$VIRTUAL_ENV/bin:$PATH
  '';

  processes = {
    web.exec = "websecmap devserver --no-backend";
    worker.exec = "websecmap celery worker -ldebug";
    broker.exec = "redis-server";
  };
}
