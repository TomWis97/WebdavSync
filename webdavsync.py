import configparser
import logging
import datetime
import os
from dateutil import parser
from webdav3.client import Client as WebdavClient

class WebDavConnection:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        
    def connect(self):
        options = {
            'webdav_hostname': self.host,
            'webdav_login': self.username,
            'webdav_password': self.password }
        self.connection = WebdavClient(options)

    def get_modified(self, path):
        modified = self.connection.info(path)['modified']
        format = '%a, %d %b %Y %X %Z'
        timestamp_tzaware = parser.parse(modified)
        # fromtimestamp() does not include the timezone.
        # So stripping it here.
        return datetime.datetime.fromtimestamp(
            timestamp_tzaware.timestamp())

    def download(self, remote_path, local_path):
        self.connection.download_file(remote_path, local_path)

    def upload(self, remote_path, local_path):
        self.connection.upload_file(remote_path, local_path)

class LocalFile:
    def __init__(self, path):
        self.path = path
        if not os.path.isfile(path):
            raise OSError("Local path is not a file.")
        
    def get_modified(self):
        stat = os.stat(self.path)
        return datetime.datetime.fromtimestamp(stat.st_mtime)

    def set_modified(self, timestamp):
        os.utime(self.path, (datetime.datetime.now().timestamp(),
                             timestamp.timestamp()))

def sync(tmp_file, connection, remote_path, local):
    with open(tmp_file, 'rt') as f:
        tmp_time = datetime.datetime.fromtimestamp(
                       int(f.read()))
    margin = datetime.timedelta(seconds=1)
    print("Time from tmp:", tmp_time)

    local_mtime = local.get_modified()
    remote_mtime = connection.get_modified(remote_path)
    
    print("Remote last modified: {} ({})".format(remote_mtime, remote_mtime.timestamp()))
    print("Local last modified: {} ({})".format(local_mtime, local_mtime.timestamp()))

    # Sanity checks. tmp_time contains last succesful sync.
    # So tmp_time should be equal to or earlier than remote/local
    if ( local_mtime < tmp_time ) or ( remote_mtime < tmp_time ):
        raise RuntimeError("Time from last sync is later than local or remote!")

    # Which files are changed?
    if ( local_mtime - tmp_time ) > margin:
        local_file_updated = True
    else:
        local_file_updated = False

    if ( remote_mtime - tmp_time ) > margin:
        remote_file_updated = True
    else:
        remote_file_updated = False

    # Both files are changed, so we have a sync conflict.
    if local_file_updated and remote_file_updated:
        with open(tmp_file, 'wt') as f:
            f.write(str(remote_mtime.timestamp()))
        raise RuntimeError("Both files are updated since last sync. Conflict!")

    if local_file_updated and not remote_file_updated:
        # Local file has been updated, so uploading it.
        print("Uploading!")
        connection.upload(remote_path, local.path)
        with open(tmp_file, 'wt') as f:
            f.write(str(int(local_mtime.timestamp())))

    if remote_file_updated and not local_file_updated:
        # Remote file has been updated, so downloading it.
        print("Downloading!")
        connection.download(remote_path, local.path)
        local.set_modified(connection.get_modified(remote_path))
        with open(tmp_file, 'wt') as f:
            f.write(str(int(remote_mtime.timestamp())))

    if not remote_file_updated and not local_file_updated:
        # Everything is up-to-date. Nothing to do.
        print("Everything is up-to-date")

    print("local_file_updated", local_file_updated)
    print("remote_file_updated", remote_file_updated)

def main():
    # Loading configuration
    config = configparser.ConfigParser()
    config.read('config.ini')

    # Connect to webdav
    c = WebDavConnection(config['connection']['host'],
                         config['connection']['username'],
                         config['connection']['password'])
    c.connect()

    # Show last modified times for debugging.
    f = LocalFile(config['file']['localpath'])

    sync(config['general']['tmp_file_path'],
         c,
         config['file']['remotepath'],
         f)

if __name__ == "__main__":
    main()
