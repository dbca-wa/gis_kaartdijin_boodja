# Standard
import logging
import os
import pathlib
import tempfile
import shutil

# Third-Party
from django import conf

# Logging
logger = logging.getLogger(__name__)


class LocalStorage():
    def __init__(self):
            self.pending_import_path = conf.settings.PENDING_IMPORT_PATH
            self.data_storage_path = conf.settings.DATA_STORAGE        

    def get_pending_import_path(self):
            return self.pending_import_path
    
    def get_data_storage_path(self):
            return self.data_storage_path

    def get_path(self, filepath):                      
            return self.pending_import_path+filepath
    def get_path_suffix(self,filepath):
            return pathlib.Path(filepath).suffix
    
    def move_to_storage(self, from_file_location, to_file_location):
        try:
            # shutil.copyfile() copies file content only (no metadata), which is important
            # for Azure Files (SMB) compatibility — metadata operations such as those
            # performed by shutil.copy2() or shutil.move() can raise errors on Azure Files.
            shutil.copyfile(from_file_location, to_file_location)
            os.unlink(from_file_location)
        except Exception as e:
            logger.error(e)
            return False
        return True
