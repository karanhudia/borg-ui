import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import DataTable, { Column, ActionButton } from '../DataTable'

// Mock types
interface TestData {
    id: number
    name: string
    role: string
    status: string
}

const mockData: TestData[] = [
    { id: 1, name: 'John Doe', role: 'Admin', status: 'Active' },
    { id: 2, name: 'Jane Smith', role: 'User', status: 'Inactive' },
    { id: 3, name: 'Bob Johnson', role: 'User', status: 'Active' },
]

const mockColumns: Column<TestData>[] = [
    { id: 'name', label: 'Name' },
    { id: 'role', label: 'Role' },
    { id: 'status', label: 'Status' },
]

describe('DataTable', () => {
    it('renders loading state correctly', () => {
        render(
            <DataTable
                data={[]}
                columns={mockColumns}
                getRowKey={(row) => row.id}
                loading={true}
            />
        )
        expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('renders empty state correctly', () => {
        const emptyState = {
            icon: <span data-testid="empty-icon">Icon</span>,
            title: 'No Data',
            description: 'Please add some data'
        }

        render(
            <DataTable
                data={[]}
                columns={mockColumns}
                getRowKey={(row) => row.id}
                emptyState={emptyState}
            />
        )

        expect(screen.getByText('No Data')).toBeInTheDocument()
        expect(screen.getByText('Please add some data')).toBeInTheDocument()
        expect(screen.getByTestId('empty-icon')).toBeInTheDocument()
    })

    it('renders table headers and data rows correctly', () => {
        render(
            <DataTable
                data={mockData}
                columns={mockColumns}
                getRowKey={(row) => row.id}
            />
        )

        // Check headers
        expect(screen.getByText('Name')).toBeInTheDocument()
        expect(screen.getByText('Role')).toBeInTheDocument()
        expect(screen.getByText('Status')).toBeInTheDocument()

        // Check data
        expect(screen.getByText('John Doe')).toBeInTheDocument()
        expect(screen.getByText('Jane Smith')).toBeInTheDocument()
        expect(screen.getByText('Bob Johnson')).toBeInTheDocument()
    })

    it('handles custom cell rendering', () => {
        const customColumns: Column<TestData>[] = [
            ...mockColumns,
            {
                id: 'actions',
                label: 'Actions',
                render: (row) => <button>Edit {row.name}</button>
            }
        ]

        render(
            <DataTable
                data={mockData}
                columns={customColumns}
                getRowKey={(row) => row.id}
            />
        )

        expect(screen.getByText('Edit John Doe')).toBeInTheDocument()
    })

    it('handles row clicks', () => {
        const handleRowClick = vi.fn()
        render(
            <DataTable
                data={mockData}
                columns={mockColumns}
                getRowKey={(row) => row.id}
                onRowClick={handleRowClick}
                enablePointer={true}
            />
        )

        fireEvent.click(screen.getByText('John Doe'))
        expect(handleRowClick).toHaveBeenCalledWith(mockData[0])
    })

    it('renders actions correctly', () => {
        const handleEdit = vi.fn()
        const handleDelete = vi.fn()

        const actions: ActionButton<TestData>[] = [
            {
                label: 'Edit',
                icon: <span>Edit</span>,
                onClick: handleEdit
            },
            {
                label: 'Delete',
                icon: <span>Delete</span>,
                onClick: handleDelete,
                color: 'error'
            }
        ]

        render(
            <DataTable
                data={mockData}
                columns={mockColumns}
                getRowKey={(row) => row.id}
                actions={actions}
            />
        )

        // Check if actions column header exists
        expect(screen.getByText('Actions')).toBeInTheDocument()

        // Click edit button for first row
        // We use getAllByRole to ensure we get the actual button, not a wrapper
        const editButtons = screen.getAllByRole('button', { name: 'Edit' })
        fireEvent.click(editButtons[0])
        expect(handleEdit).toHaveBeenCalledWith(mockData[0])
    })

    it('respects action visibility and disabled state', () => {
        const handleAction = vi.fn()
        const actions: ActionButton<TestData>[] = [
            {
                label: 'Action',
                icon: <span>Action</span>,
                onClick: handleAction,
                show: (row) => row.status === 'Active',
                disabled: (row) => row.role === 'Admin'
            }
        ]

        render(
            <DataTable
                data={mockData}
                columns={mockColumns}
                getRowKey={(row) => row.id}
                actions={actions}
            />
        )

        // We need to look for buttons specifically since Tooltip wraps them in a span
        const actionButtons = screen.getAllByRole('button', { name: 'Action' })

        // We expect 2 buttons total (John and Bob) - Jane's is hidden
        expect(actionButtons).toHaveLength(2)

        // First button (John) should be disabled
        expect(actionButtons[0]).toBeDisabled()

        // Second button (Bob) should be enabled
        expect(actionButtons[1]).not.toBeDisabled()
    })
})
