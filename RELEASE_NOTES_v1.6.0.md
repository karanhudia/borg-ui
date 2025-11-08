# v1.6.0 - Lock Error Handling & UX Improvements

## 🎯 What's New

### Lock Error Handling UI
- ✨ **User-Initiated Lock Breaking**: Added comprehensive lock error dialog across all pages
- 🔓 **LockErrorDialog Component**: New reusable component that explains lock causes and provides safe lock breaking
- 📋 **Lock Detection**: Automatic detection of repository locks (HTTP 423) with clear user prompts
- 🔄 **Auto-Retry**: Queries automatically retry after successful lock break

### Performance Improvements
- ⚡ **Faster Lock Timeout**: Reduced lock wait time from 3 minutes to 20 seconds for better UX
- 🚀 **Quick Feedback**: Users now see lock errors in ~20 seconds instead of waiting minutes

### Pages with Lock Handling
- Archives page - Full lock detection and breaking support
- Repositories page - Info dialog with lock handling
- Backup page - Lock handling for all repository operations
- Restore page - Comprehensive lock handling for archives and repository info

## 🔧 Technical Details

### Lock Dialog Features
- Explains what causes locks (crashes, network drops, container restarts)
- Safety checklist before breaking locks
- Warning about data corruption if operations are running
- One-click lock breaking with confirmation
- Automatic query invalidation and retry after lock break

### API Changes
- New endpoint: `POST /api/repositories/{repo_id}/break-lock`
- Backend returns HTTP 423 (Locked) with detailed error information
- Lock breaking now requires explicit user confirmation

## 🎨 User Experience
- Consistent lock handling across all pages
- Clear explanations of lock states
- Safe lock breaking with multiple confirmation steps
- No more silent failures or long timeout waits

## 📝 Full Changelog
- feat: add lock error dialog UI with user-initiated breaking
- feat: add lock error handling to repository info dialog
- feat: add lock error handling to Backup and Restore pages
- perf: reduce lock timeout from 3 minutes to 20 seconds
- feat: add user-initiated lock breaking with confirmation prompt

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
