import type { ReactNode } from 'react'

export interface Column<T> {
  header: string
  cell: (row: T) => ReactNode
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  empty?: string
}

function Table<T>({ columns, rows, rowKey, empty = 'Nothing here yet.' }: Props<T>) {
  if (rows.length === 0) return <p className="empty-state">{empty}</p>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.header} scope="col">{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => (
                <td key={c.header} data-label={c.header}>{c.cell(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default Table
