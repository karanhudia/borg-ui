import {
  FormControl,
  InputAdornment,
  InputLabel,
  ListSubheader,
  MenuItem,
  Select,
  TextField,
  Typography,
  type SelectChangeEvent,
  type SxProps,
  type Theme,
} from '@mui/material'
import { Search } from 'lucide-react'
import type { KeyboardEvent, MouseEvent, ReactNode } from 'react'
import { useId, useMemo, useRef, useState } from 'react'
import RichSelectRow from './RichSelectRow'

export interface RichSelectOption {
  value: string
  primary: string
  secondary?: string
  icon?: ReactNode
  iconFrame?: boolean
  indicator?: ReactNode
  disabled?: boolean
  group?: string
  searchText?: string
}

interface RichSelectProps {
  value: string
  onChange: (value: string) => void
  options: RichSelectOption[]
  label: string
  labelId?: string
  selectId?: string
  disabled?: boolean
  required?: boolean
  placeholder?: string
  searchEnabled?: boolean
  searchPlaceholder?: string
  noResultsText?: string
  sx?: SxProps<Theme>
}

export default function RichSelect({
  value,
  onChange,
  options,
  label,
  labelId,
  selectId,
  disabled,
  required,
  placeholder,
  searchEnabled = false,
  searchPlaceholder = 'Search',
  noResultsText = 'No results found',
  sx,
}: RichSelectProps) {
  const generatedId = useId()
  const resolvedLabelId = labelId ?? `${generatedId}-label`
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuWidth, setMenuWidth] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const selectedOption = options.find((option) => option.value === value)
  const normalizedSearch = search.trim().toLocaleLowerCase()
  const visibleOptions = useMemo(() => {
    if (!searchEnabled || !normalizedSearch) return options

    return options.filter((option) => {
      const text =
        option.searchText ??
        [option.primary, option.secondary, option.value].filter(Boolean).join(' ')
      return text.toLocaleLowerCase().includes(normalizedSearch)
    })
  }, [normalizedSearch, options, searchEnabled])

  const groupedOptions = useMemo(() => {
    return visibleOptions.reduce<Array<{ group?: string; options: RichSelectOption[] }>>(
      (groups, option) => {
        const lastGroup = groups[groups.length - 1]
        if (lastGroup && lastGroup.group === option.group) {
          lastGroup.options.push(option)
        } else {
          groups.push({ group: option.group, options: [option] })
        }
        return groups
      },
      []
    )
  }, [visibleOptions])

  const handleOpen = () => {
    setSearch('')
    setMenuWidth(rootRef.current?.getBoundingClientRect().width ?? null)
    setMenuOpen(true)
  }

  const handleSearchClick = (event: MouseEvent) => {
    event.stopPropagation()
  }

  const handleSearchKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') {
      event.stopPropagation()
    }
  }

  return (
    <FormControl fullWidth disabled={disabled} required={required} sx={sx} ref={rootRef}>
      <InputLabel id={resolvedLabelId} shrink={Boolean(placeholder) || undefined}>
        {label}
      </InputLabel>
      <Select
        labelId={resolvedLabelId}
        id={selectId}
        value={selectedOption ? selectedOption.value : value}
        label={label}
        displayEmpty={Boolean(placeholder)}
        open={menuOpen}
        onOpen={handleOpen}
        onClose={() => setMenuOpen(false)}
        onChange={(event: SelectChangeEvent<string>) => {
          onChange(event.target.value)
          setMenuOpen(false)
        }}
        renderValue={(selected) => {
          if (selected === '' && placeholder) {
            return (
              <Typography variant="body2" color="text.secondary" noWrap>
                {placeholder}
              </Typography>
            )
          }

          const option = options.find((item) => item.value === selected)
          if (!option) return null

          return <RichSelectOptionRow option={option} />
        }}
        MenuProps={{
          autoFocus: !searchEnabled,
          MenuListProps: {
            autoFocusItem: !searchEnabled,
            sx: {
              width: '100%',
              py: 0.5,
            },
          },
          PaperProps: {
            sx: {
              mt: 0.5,
              width: menuWidth ?? undefined,
              minWidth: menuWidth ?? undefined,
              maxWidth: menuWidth ?? undefined,
              maxHeight: 430,
              overflowX: 'hidden',
            },
          },
        }}
        sx={{
          height: 56,
          '& .MuiSelect-select': {
            height: 56,
            boxSizing: 'border-box',
            display: 'flex',
            alignItems: 'center',
            minWidth: 0,
            py: 0,
            pl: 1,
            pr: 4,
          },
        }}
      >
        {searchEnabled && (
          <ListSubheader
            sx={{
              bgcolor: 'background.paper',
              lineHeight: 'normal',
              px: 1,
              pt: 1,
              pb: 0.75,
            }}
          >
            <TextField
              autoFocus
              fullWidth
              size="small"
              value={search}
              placeholder={searchPlaceholder}
              onChange={(event) => setSearch(event.target.value)}
              onClick={handleSearchClick}
              onMouseDown={handleSearchClick}
              onKeyDown={handleSearchKeyDown}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search size={14} />
                  </InputAdornment>
                ),
              }}
            />
          </ListSubheader>
        )}
        {placeholder && (
          <MenuItem disabled value="" sx={menuItemSx}>
            <Typography variant="body2" color="text.secondary" noWrap>
              {placeholder}
            </Typography>
          </MenuItem>
        )}
        {groupedOptions.length ? (
          groupedOptions.flatMap(({ group, options: groupOptions }, groupIndex) => [
            group ? (
              <ListSubheader
                key={`group-${groupIndex}-${group}`}
                disableSticky
                sx={{
                  bgcolor: 'background.paper',
                  color: 'text.secondary',
                  fontWeight: 600,
                  lineHeight: 1.5,
                  px: 2,
                  pt: 1.25,
                  pb: 0.5,
                }}
              >
                {group}
              </ListSubheader>
            ) : null,
            ...groupOptions.map((option) => (
              <MenuItem
                key={option.value}
                value={option.value}
                disabled={option.disabled}
                sx={menuItemSx}
              >
                <RichSelectOptionRow option={option} />
              </MenuItem>
            )),
          ])
        ) : (
          <MenuItem disabled sx={menuItemSx}>
            <Typography variant="body2" color="text.secondary" noWrap>
              {noResultsText}
            </Typography>
          </MenuItem>
        )}
      </Select>
    </FormControl>
  )
}

function RichSelectOptionRow({ option }: { option: RichSelectOption }) {
  return (
    <RichSelectRow
      icon={option.icon}
      iconFrame={option.iconFrame}
      primary={option.primary}
      secondary={option.secondary}
      indicator={option.indicator}
    />
  )
}

const menuItemSx = {
  width: '100%',
  maxWidth: '100%',
  minWidth: 0,
  px: 1,
  py: 1,
}
