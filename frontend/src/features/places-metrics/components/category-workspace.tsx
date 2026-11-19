import { Link } from 'react-router-dom'

import { Pager } from '@/features/places-metrics/components/pager'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import { PlaceReceipt } from '@/features/places-metrics/components/place-receipt'
import { RequirementTable } from '@/features/places-metrics/components/requirement-table'
import { SortBar } from '@/features/places-metrics/components/sort-bar'
import { StatusMark } from '@/features/places-metrics/components/status-mark'
import type { Category, SortMode, Status } from '@/features/places-metrics/types/placesMetrics'
import { STATUS_LABEL, STATUSES } from '@/features/places-metrics/utils/fit'
import type { PageWindow } from '@/features/places-metrics/utils/paging'
import type { ReceiptView } from '@/features/places-metrics/utils/receipt'
import type { ColumnHead, TableRow } from '@/features/places-metrics/utils/requirementTable'

type CategoryWorkspaceProps = {
  category: Category
  sort: SortMode
  timeLabel: string
  columns: PageWindow
  heads: ColumnHead[]
  rows: TableRow[]
  receipt: ReceiptView | null
  checkedOn: string | null
  onSort: (mode: SortMode) => void
  onPageColumns: (start: number) => void
  onPickPlace: (placeKey: string) => void
  onPickQuestion: (placeKey: string, questionId: string) => void
  onCloseReceipt: () => void
}

/** The active category: sortable requirement table, its legend, then the open place's proof. */
export function CategoryWorkspace(props: CategoryWorkspaceProps) {
  const { category, sort, timeLabel, columns, heads, rows, receipt, checkedOn } = props
  return (
    <div className="workspace">
      {!category.asked ? (
        <h2 className="also">
          Also worth knowing <span>· not in your brief, added because they usually matter</span>
        </h2>
      ) : null}
      <section className="panel ws" aria-labelledby={`ws-${category.key}`}>
        <div className="ws-head">
          <span className="tile ws-tile" style={{ color: category.color }}>
            <PathIcon d={category.icon} size={20} strokeWidth={1.7} />
          </span>
          <div className="ws-titles">
            <h2 id={`ws-${category.key}`} className="ws-title">
              {category.name}
            </h2>
            <span className="num ws-count">
              No. of requirements: <b>{category.questions.length}</b>
            </span>
          </div>
          <Link to="/proximity_info" className="ws-link">
            Places and travel times
          </Link>
        </div>

        <div className="mxcard">
          <SortBar categoryKey={category.key} sort={sort} onSort={props.onSort} />
          {columns.paged ? <Pager window={columns} onPage={props.onPageColumns} /> : null}
          <RequirementTable
            categoryName={category.name}
            color={category.color}
            timeLabel={timeLabel}
            heads={heads}
            rows={rows}
            onPickPlace={props.onPickPlace}
          />
          <div className="tc-legend">
            {STATUSES.map((s: Status) => (
              <span key={s} className="tc-lg">
                <StatusMark status={s} small />
                {STATUS_LABEL[s]}
              </span>
            ))}
          </div>
        </div>

        {receipt ? (
          <PlaceReceipt
            receipt={receipt}
            checkedOn={checkedOn}
            onPickQuestion={(q) => props.onPickQuestion(receipt.key, q)}
            onClose={props.onCloseReceipt}
          />
        ) : (
          <p className="nosel">Pick a place or any answer above to see its proof here.</p>
        )}
      </section>
    </div>
  )
}
