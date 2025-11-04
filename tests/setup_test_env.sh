#!/bin/bash
###############################################################################
# Borg UI Test Environment Setup
#
# This script creates a comprehensive test environment for Borg UI including:
# - Test Borg repositories with various structures
# - Test data with multiple folders and files
# - Archives with different content patterns
#
# Usage: ./setup_test_env.sh [test_dir]
# Default test_dir: /tmp/borg-ui-tests
###############################################################################

set -e  # Exit on error

TEST_DIR="${1:-/tmp/borg-ui-tests}"
REPO_DIR="$TEST_DIR/repositories"
SOURCE_DIR="$TEST_DIR/source_data"
TEMP_DIR="$TEST_DIR/temp"

echo "=================================================="
echo "Borg UI Test Environment Setup"
echo "=================================================="
echo "Test directory: $TEST_DIR"
echo ""

# Check if borg is installed
if ! command -v borg &> /dev/null; then
    echo "❌ Error: borg command not found"
    echo "Please install borgbackup first:"
    echo "  - macOS: brew install borgbackup"
    echo "  - Ubuntu/Debian: apt install borgbackup"
    echo "  - Arch: pacman -S borg"
    exit 1
fi

echo "✅ Found borg version: $(borg --version)"
echo ""

# Clean up old test directory if it exists
if [ -d "$TEST_DIR" ]; then
    echo "🧹 Cleaning up old test directory..."
    rm -rf "$TEST_DIR"
fi

# Create directory structure
echo "📁 Creating directory structure..."
mkdir -p "$REPO_DIR"
mkdir -p "$SOURCE_DIR"
mkdir -p "$TEMP_DIR"

###############################################################################
# Create Test Source Data
###############################################################################

echo ""
echo "📝 Creating test source data..."

# Create a complex directory structure with multiple root folders
# This simulates a real backup scenario with various content types

# Folder 1: Documents (simulating user documents)
mkdir -p "$SOURCE_DIR/Documents/Work/Projects"
mkdir -p "$SOURCE_DIR/Documents/Personal"
echo "Important work document" > "$SOURCE_DIR/Documents/Work/Projects/report.txt"
echo "Meeting notes" > "$SOURCE_DIR/Documents/Work/notes.txt"
echo "Personal letter" > "$SOURCE_DIR/Documents/Personal/letter.txt"

# Folder 2: Photos (simulating media files)
mkdir -p "$SOURCE_DIR/Photos/2024/January"
mkdir -p "$SOURCE_DIR/Photos/2024/February"
mkdir -p "$SOURCE_DIR/Photos/2023"
echo "photo1 data" > "$SOURCE_DIR/Photos/2024/January/photo1.jpg"
echo "photo2 data" > "$SOURCE_DIR/Photos/2024/January/photo2.jpg"
echo "photo3 data" > "$SOURCE_DIR/Photos/2024/February/photo3.jpg"
echo "old photo" > "$SOURCE_DIR/Photos/2023/old_photo.jpg"

# Folder 3: Code (simulating development projects)
mkdir -p "$SOURCE_DIR/Code/project1/src"
mkdir -p "$SOURCE_DIR/Code/project2/tests"
echo "console.log('hello');" > "$SOURCE_DIR/Code/project1/src/index.js"
echo "# Project 1" > "$SOURCE_DIR/Code/project1/README.md"
echo "def test(): pass" > "$SOURCE_DIR/Code/project2/tests/test.py"

# Folder 4: Videos (larger files)
mkdir -p "$SOURCE_DIR/Videos/Tutorials"
mkdir -p "$SOURCE_DIR/Videos/Personal"
echo "video data placeholder" > "$SOURCE_DIR/Videos/Tutorials/tutorial1.mp4"
echo "video data placeholder" > "$SOURCE_DIR/Videos/Personal/vacation.mp4"

# Folder 5-16: Additional folders to test the "16 folders" scenario
for i in {5..16}; do
    mkdir -p "$SOURCE_DIR/Folder$i/Subfolder"
    echo "Test file in folder $i" > "$SOURCE_DIR/Folder$i/file$i.txt"
    echo "Nested file in folder $i" > "$SOURCE_DIR/Folder$i/Subfolder/nested$i.txt"
done

# Create some hidden files (dotfiles)
echo "config data" > "$SOURCE_DIR/.config"
mkdir -p "$SOURCE_DIR/.hidden_folder"
echo "hidden data" > "$SOURCE_DIR/.hidden_folder/data.txt"

# Count what we created
FOLDER_COUNT=$(find "$SOURCE_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
FILE_COUNT=$(find "$SOURCE_DIR" -type f | wc -l)
echo "  ✅ Created $FOLDER_COUNT root folders"
echo "  ✅ Created $FILE_COUNT total files"

###############################################################################
# Create Test Repositories
###############################################################################

echo ""
echo "🗄️  Creating test repositories..."

# Repository 1: Standard unencrypted repo (easiest for testing)
REPO1="$REPO_DIR/repo1-unencrypted"
echo ""
echo "Creating Repository 1: Unencrypted (for easy testing)"
borg init --encryption=none "$REPO1"
echo "  ✅ Repository initialized: $REPO1"

# Create first archive with all data
echo "  📦 Creating archive 'test-full-backup'..."
borg create --stats "$REPO1::test-full-backup" "$SOURCE_DIR"

# Create second archive with partial data (only Documents and Photos)
echo "  📦 Creating archive 'test-partial-backup'..."
borg create --stats "$REPO1::test-partial-backup" \
    "$SOURCE_DIR/Documents" \
    "$SOURCE_DIR/Photos"

# Create third archive with single folder
echo "  📦 Creating archive 'test-single-folder'..."
borg create --stats "$REPO1::test-single-folder" \
    "$SOURCE_DIR/Code"

echo "  ✅ Created 3 archives in repo1"

# Repository 2: Encrypted with passphrase
REPO2="$REPO_DIR/repo2-encrypted"
PASSPHRASE="test123"
echo ""
echo "Creating Repository 2: Encrypted (passphrase: test123)"
BORG_PASSPHRASE="$PASSPHRASE" borg init --encryption=repokey "$REPO2"
echo "  ✅ Repository initialized: $REPO2"

echo "  📦 Creating archive 'encrypted-backup'..."
BORG_PASSPHRASE="$PASSPHRASE" borg create --stats "$REPO2::encrypted-backup" \
    "$SOURCE_DIR"
echo "  ✅ Created 1 archive in repo2"

# Repository 3: Large repository (for performance testing)
REPO3="$REPO_DIR/repo3-large"
echo ""
echo "Creating Repository 3: Large repository (for performance testing)"
borg init --encryption=none "$REPO3"

# Create temporary large dataset
echo "  📝 Creating large test dataset..."
LARGE_DATA="$TEMP_DIR/large_data"
mkdir -p "$LARGE_DATA"

# Create 100 folders with 50 files each = 5000 files total
for i in {1..100}; do
    mkdir -p "$LARGE_DATA/folder_$i"
    for j in {1..50}; do
        echo "File $j in folder $i" > "$LARGE_DATA/folder_$i/file_$j.txt"
    done
done

LARGE_FILE_COUNT=$(find "$LARGE_DATA" -type f | wc -l)
echo "  ✅ Created $LARGE_FILE_COUNT files for large repo"

echo "  📦 Creating archive 'large-backup'..."
borg create --stats "$REPO3::large-backup" "$LARGE_DATA"
echo "  ✅ Created 1 archive in repo3"

# Clean up large data temp folder
rm -rf "$LARGE_DATA"

###############################################################################
# Create Test Info File
###############################################################################

INFO_FILE="$TEST_DIR/TEST_INFO.txt"
cat > "$INFO_FILE" << EOF
================================================
Borg UI Test Environment Information
================================================
Created: $(date)
Location: $TEST_DIR

REPOSITORIES:
-------------

1. repo1-unencrypted ($REPO1)
   - Encryption: None
   - Archives: 3
     * test-full-backup: All source data ($FOLDER_COUNT folders)
     * test-partial-backup: Documents + Photos only
     * test-single-folder: Code folder only
   - Use for: Testing archive browsing with multiple root folders

2. repo2-encrypted ($REPO2)
   - Encryption: repokey
   - Passphrase: test123
   - Archives: 1
     * encrypted-backup: All source data
   - Use for: Testing encrypted repository access

3. repo3-large ($REPO3)
   - Encryption: None
   - Archives: 1
     * large-backup: 100 folders, ~5000 files
   - Use for: Performance testing, pagination testing

SOURCE DATA:
------------
Location: $SOURCE_DIR
Root folders: $FOLDER_COUNT
Total files: $FILE_COUNT

Structure:
- Documents/      (Work docs, Personal docs)
- Photos/         (2023, 2024 with subfolders)
- Code/           (project1, project2)
- Videos/         (Tutorials, Personal)
- Folder5-16/     (Test folders with subfolders)
- .config         (Hidden file)
- .hidden_folder/ (Hidden directory)

TESTING COMMANDS:
-----------------

List archives in repo1:
  borg list $REPO1

List contents of test-full-backup at root:
  borg list --json-lines $REPO1::test-full-backup

List contents of specific folder:
  borg list --json-lines $REPO1::test-full-backup Documents

Mount an archive (for comparison testing):
  mkdir /tmp/borg-mount
  borg mount $REPO1::test-full-backup /tmp/borg-mount
  ls -la /tmp/borg-mount
  borg umount /tmp/borg-mount

Test encrypted repo (repo2):
  BORG_PASSPHRASE=test123 borg list $REPO2

BORG UI TESTING:
----------------

1. Add repositories to Borg UI:
   - Type: Local
   - Path: $REPO1 (or repo2, repo3)
   - Passphrase: (none for repo1/repo3, "test123" for repo2)

2. Test archive browsing:
   - View archives list
   - Browse test-full-backup root (should show $FOLDER_COUNT folders)
   - Navigate into Documents/Work/Projects
   - Compare with: borg list output

3. Test restore functionality:
   - Select files from different folders
   - Test restore to /tmp/restore-test
   - Verify restored files match originals

4. Test search/filter:
   - Search for .txt files
   - Filter by folder name
   - Test with large-backup (5000 files)

CLEANUP:
--------
To remove test environment:
  rm -rf $TEST_DIR

================================================
EOF

echo ""
echo "📄 Test information saved to: $INFO_FILE"

###############################################################################
# Summary
###############################################################################

echo ""
echo "=================================================="
echo "✅ Test Environment Setup Complete!"
echo "=================================================="
echo ""
echo "Test directory: $TEST_DIR"
echo ""
echo "Created repositories:"
echo "  1. $REPO1 (3 archives, unencrypted)"
echo "  2. $REPO2 (1 archive, encrypted with 'test123')"
echo "  3. $REPO3 (1 archive, large dataset)"
echo ""
echo "Source data: $SOURCE_DIR ($FOLDER_COUNT folders, $FILE_COUNT files)"
echo ""
echo "📖 See $INFO_FILE for detailed information"
echo ""
echo "Next steps:"
echo "  1. Read: cat $INFO_FILE"
echo "  2. Test borg commands manually (see info file)"
echo "  3. Add repositories to Borg UI and test browsing"
echo "  4. Run: python tests/test_archive_contents.py $TEST_DIR"
echo ""
