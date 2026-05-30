from package_client import build_client_bundle
from package_server import build_server_bundle


def main():
    client_zip = build_client_bundle()
    server_zip = build_server_bundle()
    print(client_zip)
    print(server_zip)


if __name__ == "__main__":
    main()
