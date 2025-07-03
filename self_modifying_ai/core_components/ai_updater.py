import os
import shutil
import datetime
import logging

# Configure basic logging for the updater module
logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid adding multiple handlers if reloaded
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class AIUpdaterError(Exception):
    """Base exception for AIUpdater errors."""
    pass

class FileOperationError(AIUpdaterError):
    """Exception raised for errors during file operations."""
    pass

class AIUpdater:
    def __init__(self, base_code_dir: str, staging_dir: str = "staging", backup_dir: str = "backup"):
        self.base_code_dir = os.path.abspath(base_code_dir)
        self.staging_dir = os.path.abspath(staging_dir)
        self.backup_dir = os.path.abspath(backup_dir)

        self._ensure_dirs_exist()
        logger.info(f"AIUpdater initialized. Base code dir: {self.base_code_dir}, Staging: {self.staging_dir}, Backup: {self.backup_dir}")

    def _ensure_dirs_exist(self):
        """Ensures that staging and backup directories exist."""
        try:
            os.makedirs(self.staging_dir, exist_ok=True)
            os.makedirs(self.backup_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Error creating essential directories: {e}")
            raise FileOperationError(f"Could not create staging/backup directories: {e}")

    def stage_code_from_source(self, source_path: str, relative_target_path: str) -> str:
        """
        Copies code from a source path to the staging directory.
        The source can be a file or a directory.
        'relative_target_path' is the path within the staging directory where the code will be placed.
        It should mirror the intended path within the base_code_dir.

        Args:
            source_path (str): The path to the source file or directory.
            relative_target_path (str): The relative path within the staging area.

        Returns:
            str: The full path to the staged code in the staging directory.

        Raises:
            FileNotFoundError: If the source_path does not exist.
            FileOperationError: If copying fails.
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source path '{source_path}' not found.")

        staged_path = os.path.join(self.staging_dir, relative_target_path)
        staged_item_dir = os.path.dirname(staged_path)

        try:
            if staged_item_dir: # Ensure parent directory exists in staging
                os.makedirs(staged_item_dir, exist_ok=True)

            if os.path.isdir(source_path):
                if os.path.exists(staged_path): # If staging dir exists, remove it first
                    shutil.rmtree(staged_path)
                shutil.copytree(source_path, staged_path)
                logger.info(f"Directory '{source_path}' staged to '{staged_path}'.")
            else: # It's a file
                shutil.copy2(source_path, staged_path) # copy2 preserves metadata
                logger.info(f"File '{source_path}' staged to '{staged_path}'.")
            return staged_path
        except Exception as e:
            logger.error(f"Error staging code from '{source_path}' to '{staged_path}': {e}")
            raise FileOperationError(f"Failed to stage code: {e}")

    def backup_module_or_file(self, relative_path: str) -> str | None:
        """
        Backs up a module (file or directory) from the base_code_dir to the backup_dir.
        The relative_path is the path of the item within base_code_dir.
        A timestamp is added to the backup to preserve multiple versions.

        Args:
            relative_path (str): The path relative to base_code_dir of the module/file to back up.

        Returns:
            str: Full path to the created backup. None if the source doesn't exist.

        Raises:
            FileOperationError: If backup fails.
        """
        source_full_path = os.path.join(self.base_code_dir, relative_path)
        if not os.path.exists(source_full_path):
            logger.warning(f"Cannot backup '{relative_path}': Source '{source_full_path}' does not exist.")
            return None

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # Sanitize relative_path for use in backup filename/dirname
        sanitized_relative_path = relative_path.replace(os.sep, '_')
        backup_name = f"{sanitized_relative_path}.{timestamp}"
        backup_path_in_backup_dir = os.path.join(self.backup_dir, backup_name)

        # If backing up a file that's part of a path, ensure parent dir in backup
        backup_item_parent_dir = os.path.dirname(backup_path_in_backup_dir)
        if backup_item_parent_dir:
             os.makedirs(backup_item_parent_dir, exist_ok=True)


        try:
            if os.path.isdir(source_full_path):
                shutil.copytree(source_full_path, backup_path_in_backup_dir)
                logger.info(f"Directory '{source_full_path}' backed up to '{backup_path_in_backup_dir}'.")
            else: # It's a file
                shutil.copy2(source_full_path, backup_path_in_backup_dir)
                logger.info(f"File '{source_full_path}' backed up to '{backup_path_in_backup_dir}'.")
            return backup_path_in_backup_dir
        except Exception as e:
            logger.error(f"Error backing up '{source_full_path}' to '{backup_path_in_backup_dir}': {e}")
            raise FileOperationError(f"Failed to backup module/file: {e}")

    def apply_staged_update(self, relative_staged_path: str) -> str:
        """
        Applies an update from the staging directory to the base_code_dir.
        'relative_staged_path' is the path of the item within the staging dir,
        which should mirror its intended final path within base_code_dir.

        Important: This will overwrite existing files/directories in base_code_dir.
        It's recommended to call backup_module_or_file before this.

        Args:
            relative_staged_path (str): The path of the staged item, relative to staging_dir.

        Returns:
            str: The full path to the updated code in the base_code_dir.

        Raises:
            FileNotFoundError: If the staged item does not exist.
            FileOperationError: If applying the update fails.
        """
        staged_item_full_path = os.path.join(self.staging_dir, relative_staged_path)
        if not os.path.exists(staged_item_full_path):
            raise FileNotFoundError(f"Staged item '{staged_item_full_path}' not found.")

        target_path_in_base_code = os.path.join(self.base_code_dir, relative_staged_path)
        target_item_parent_dir = os.path.dirname(target_path_in_base_code)

        try:
            if target_item_parent_dir: # Ensure parent directory exists in target
                os.makedirs(target_item_parent_dir, exist_ok=True)

            # If target exists, remove it before copying from staging
            if os.path.isdir(target_path_in_base_code):
                shutil.rmtree(target_path_in_base_code)
            elif os.path.isfile(target_path_in_base_code):
                os.remove(target_path_in_base_code)

            # Now copy from staging to target
            if os.path.isdir(staged_item_full_path):
                shutil.copytree(staged_item_full_path, target_path_in_base_code)
                logger.info(f"Staged directory '{staged_item_full_path}' applied to '{target_path_in_base_code}'.")
            else: # It's a file
                shutil.copy2(staged_item_full_path, target_path_in_base_code)
                logger.info(f"Staged file '{staged_item_full_path}' applied to '{target_path_in_base_code}'.")
            return target_path_in_base_code
        except Exception as e:
            logger.error(f"Error applying update from '{staged_item_full_path}' to '{target_path_in_base_code}': {e}")
            raise FileOperationError(f"Failed to apply staged update: {e}")

    def clear_staging_area(self, relative_path: str = None):
        """
        Clears a specific item or the entire staging area.
        Args:
            relative_path (str, optional): If provided, removes this specific item from staging.
                                           Otherwise, clears the entire staging directory.
        """
        if relative_path:
            path_to_clear = os.path.join(self.staging_dir, relative_path)
            if os.path.exists(path_to_clear):
                if os.path.isdir(path_to_clear):
                    shutil.rmtree(path_to_clear)
                    logger.info(f"Cleared directory '{path_to_clear}' from staging area.")
                else:
                    os.remove(path_to_clear)
                    logger.info(f"Cleared file '{path_to_clear}' from staging area.")
            else:
                logger.warning(f"Path '{path_to_clear}' not found in staging area for clearing.")
        else:
            shutil.rmtree(self.staging_dir)
            os.makedirs(self.staging_dir, exist_ok=True) # Recreate the empty dir
            logger.info(f"Entire staging area '{self.staging_dir}' cleared.")


if __name__ == '__main__':
    # Setup a temporary directory structure for testing
    TEST_ROOT_DIR = os.path.abspath("ai_updater_test_area")
    BASE_CODE = os.path.join(TEST_ROOT_DIR, "my_ai_code")
    STAGING = os.path.join(TEST_ROOT_DIR, "ai_staging")
    BACKUP = os.path.join(TEST_ROOT_DIR, "ai_backup")
    EXTERNAL_SOURCE = os.path.join(TEST_ROOT_DIR, "external_source_code")

    def setup_test_env():
        if os.path.exists(TEST_ROOT_DIR):
            shutil.rmtree(TEST_ROOT_DIR)
        os.makedirs(BASE_CODE, exist_ok=True)
        os.makedirs(EXTERNAL_SOURCE, exist_ok=True)

        # Create some initial files in base_code_dir
        with open(os.path.join(BASE_CODE, "module_a.py"), "w") as f:
            f.write("# Original Module A\nversion = 1.0\n")
        os.makedirs(os.path.join(BASE_CODE, "package1"), exist_ok=True)
        with open(os.path.join(BASE_CODE, "package1", "mod_b.py"), "w") as f:
            f.write("# Original Module B in Package 1\nversion = 1.0\n")
        with open(os.path.join(BASE_CODE, "package1", "__init__.py"), "w") as f:
            f.write("# Package 1 init\n")

        # Create some source files to "update" from
        with open(os.path.join(EXTERNAL_SOURCE, "module_a_v2.py"), "w") as f:
            f.write("# Updated Module A\nversion = 2.0\n")
        os.makedirs(os.path.join(EXTERNAL_SOURCE, "new_package"), exist_ok=True)
        with open(os.path.join(EXTERNAL_SOURCE, "new_package", "mod_c.py"), "w") as f:
            f.write("# New Module C in New Package\nversion = 1.0\n")
        with open(os.path.join(EXTERNAL_SOURCE, "new_package", "__init__.py"), "w") as f:
            f.write("# New Package init\n")

    def cleanup_test_env():
        if os.path.exists(TEST_ROOT_DIR):
            shutil.rmtree(TEST_ROOT_DIR)

    print("--- AIUpdater Example ---")
    setup_test_env()

    updater = AIUpdater(base_code_dir=BASE_CODE, staging_dir=STAGING, backup_dir=BACKUP)

    try:
        # 1. Stage a file update
        print("\n1. Staging module_a.py update...")
        staged_module_a_path = updater.stage_code_from_source(
            os.path.join(EXTERNAL_SOURCE, "module_a_v2.py"),
            "module_a.py" # Relative path for staging and eventual application
        )
        print(f"Staged 'module_a.py' to: {staged_module_a_path}")
        assert os.path.exists(staged_module_a_path)

        # 2. Stage a new package
        print("\n2. Staging new_package...")
        staged_new_package_path = updater.stage_code_from_source(
            os.path.join(EXTERNAL_SOURCE, "new_package"),
            "new_package" # Relative path for the new package
        )
        print(f"Staged 'new_package' to: {staged_new_package_path}")
        assert os.path.exists(os.path.join(staged_new_package_path, "mod_c.py"))

        # 3. Backup existing module_a.py before updating
        print("\n3. Backing up original module_a.py...")
        backup_path_module_a = updater.backup_module_or_file("module_a.py")
        print(f"Backed up 'module_a.py' to: {backup_path_module_a}")
        assert backup_path_module_a and os.path.exists(backup_path_module_a)
        with open(backup_path_module_a, "r") as f:
            assert "version = 1.0" in f.read() # Check it's the original

        # 4. Apply the staged update for module_a.py
        print("\n4. Applying staged update for module_a.py...")
        applied_module_a_path = updater.apply_staged_update("module_a.py")
        print(f"Applied 'module_a.py' to: {applied_module_a_path}")
        assert os.path.exists(applied_module_a_path)
        with open(applied_module_a_path, "r") as f:
            content = f.read()
            assert "version = 2.0" in content, f"Content was: {content}"


        # 5. Backup existing package1 (even though we are not updating it, just for demo)
        print("\n5. Backing up original package1...")
        backup_path_package1 = updater.backup_module_or_file("package1")
        print(f"Backed up 'package1' to: {backup_path_package1}")
        assert backup_path_package1 and os.path.exists(os.path.join(backup_path_package1, "mod_b.py"))


        # 6. Apply the staged new_package
        print("\n6. Applying staged new_package...")
        applied_new_package_path = updater.apply_staged_update("new_package")
        print(f"Applied 'new_package' to: {applied_new_package_path}")
        assert os.path.exists(os.path.join(applied_new_package_path, "mod_c.py"))
        assert os.path.exists(os.path.join(BASE_CODE, "new_package", "mod_c.py")) # Verify in base

        # 7. Check contents of backup and staging directories
        print("\n7. Verifying backup and staging contents...")
        assert len(os.listdir(updater.backup_dir)) >= 2 # module_a and package1 backups
        print(f"Backup directory contents: {os.listdir(updater.backup_dir)}")
        # Staging dir should still have items until cleared
        assert os.path.exists(os.path.join(updater.staging_dir, "module_a.py"))
        assert os.path.exists(os.path.join(updater.staging_dir, "new_package"))
        print(f"Staging directory contents: {os.listdir(updater.staging_dir)}")


        # 8. Clear a specific item from staging
        print("\n8. Clearing 'module_a.py' from staging...")
        updater.clear_staging_area("module_a.py")
        assert not os.path.exists(os.path.join(updater.staging_dir, "module_a.py"))
        assert os.path.exists(os.path.join(updater.staging_dir, "new_package")) # new_package should still be there
        print(f"Staging directory after clearing module_a.py: {os.listdir(updater.staging_dir)}")

        # 9. Clear entire staging area
        print("\n9. Clearing entire staging area...")
        updater.clear_staging_area()
        assert not os.listdir(updater.staging_dir) # Staging should be empty
        print(f"Staging directory after full clear: {os.listdir(updater.staging_dir)}")


        # Test backing up non-existent file
        print("\n10. Test backing up non-existent file...")
        non_existent_backup = updater.backup_module_or_file("non_existent.py")
        assert non_existent_backup is None
        print("Backup of non-existent file handled correctly (returned None).")

        print("\n--- AIUpdater Example Completed Successfully ---")

    except (AIUpdaterError, FileNotFoundError, AssertionError) as e:
        logger.error(f"An error occurred during AIUpdater example: {e}", exc_info=True)
        print(f"AIUpdater Example FAILED: {e}")
    finally:
        cleanup_test_env()
        print("Test environment cleaned up.")
