import { Box, Typography } from '@mui/material'
import Editor from '@monaco-editor/react'

interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  label?: string
  helperText?: string
  placeholder?: string
  height?: string
  language?: string
}

export default function CodeEditor({
  value,
  onChange,
  label,
  helperText,
  placeholder: _placeholder = '#!/bin/bash\n',
  height = '180px',
  language = 'shell',
}: CodeEditorProps) {
  return (
    <Box sx={{ mb: 2 }}>
      {label && (
        <Typography variant="subtitle2" sx={{ mb: 0.5, fontWeight: 500 }}>
          {label}
        </Typography>
      )}
      <Box
        sx={{
          border: '2px solid',
          borderColor: 'divider',
          borderRadius: 1,
          overflow: 'hidden',
          transition: 'border-color 0.2s',
          '&:hover': {
            borderColor: 'text.secondary',
          },
          '&:focus-within': {
            borderColor: 'primary.main',
          },
        }}
      >
        <Editor
          height={height}
          language={language}
          value={value || ''}
          onChange={(val) => onChange(val || '')}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: 'on',
            lineNumbersMinChars: 3,
            glyphMargin: false,
            folding: false,
            lineDecorationsWidth: 5,
            roundedSelection: false,
            scrollBeyondLastLine: false,
            readOnly: false,
            automaticLayout: true,
            tabSize: 2,
            wordWrap: 'on',
            wrappingIndent: 'indent',
            padding: { top: 8, bottom: 8 },
            suggest: {
              showKeywords: true,
              showSnippets: true,
            },
            quickSuggestions: {
              other: true,
              comments: true,
              strings: true,
            },
          }}
          loading={<Box sx={{ p: 2, backgroundColor: '#1e1e1e' }}>Loading editor...</Box>}
        />
      </Box>
      {helperText && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {helperText}
        </Typography>
      )}
    </Box>
  )
}
