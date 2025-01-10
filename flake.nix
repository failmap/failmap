{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    # we pin to a specific version of nuclei to prevent is from changes from
    # under us and introducing bugs
    nuclei.url = "github:NixOS/nixpkgs/8549e57eceb5428c44b6b6e8cfe25d11a8715bfe";
  };

  outputs = { self, nixpkgs, flake-utils, nuclei }:
    flake-utils.lib.eachDefaultSystem (system:
        let
        pkgs = import nixpkgs {
            system = system;
            overlays = [
                (final: prev: { pkgs-nuclei = nuclei.legacyPackages.${prev.system}; })
            ];
        }; in {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
              # development requirements
              git
              gnumake

              # Python version to use
              python310

              # required for building MySQL Python package
              libmysqlclient.dev
              postgresql

              # required for running dev environment
              redis
              nmap

              # additional tools
              shellcheck

              # scanner dependencies
              pkgs-nuclei.nuclei
              nuclei-templates
          ];
          env = {
              DEBUG = 1;
              NETWORK_SUPPORTS_IPV6 = 1;
              PIP_DISABLE_PIP_VERSION_CHECK = 1;
              DJANGO_SETTINGS_MODULE = "websecmap.settings";
              MYSQLCLIENT_CFLAGS = "-I${pkgs.libmysqlclient.dev}/include/mysql";
              MYSQLCLIENT_LDFLAGS = "-L${pkgs.libmysqlclient.dev}/lib";
              NUCLEI_BIN = "${pkgs.pkgs-nuclei.nuclei}/bin/nuclei";
              PROJECT_WEBSITE = "http://localhost:8000";
              LD_LIBRARY_PATH= "${pkgs.stdenv.cc.cc.lib}/lib/";
          };
          shellHook = ''
            python_version=$(python --version)
            echo $python_version

            # find a suitable place to create virtual environment outside of project directory
            if test "$(uname -s)" = "Darwin";then
                export VIRTUAL_ENV=~/Library/Caches/virtualenvs/$(basename $PWD)-''${python_version/\ /_}
            else
                export VIRTUAL_ENV=''${XDG_CACHE_HOME:-~/.cache}/virtualenvs/$(basename $PWD)-''${python_version/\ /_}
            fi
            echo "Virtualenv: $VIRTUAL_ENV"

            export PATH=$VIRTUAL_ENV/bin:$PATH
          '';
        };
    });
}
