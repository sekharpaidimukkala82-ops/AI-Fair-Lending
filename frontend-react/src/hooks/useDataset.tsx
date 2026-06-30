/**
 * useDataset hook — wraps useDatasetStore for compatibility with P3/P4 pages.
 * P3/P4 pages use `useDataset()` returning `{ activeDataset, setActiveDataset }`.
 * Our system stores datasets in useDatasetStore with `selectedId` + `getSelected()`.
 */
import { useDatasetStore } from '../store/datasetStore'

export interface DatasetInfo {
  file_id: string
  filename: string
  original_filename?: string
  total_rows?: number
  total_columns?: number
  quality_score?: number
  dataset_type?: string
  status?: string
}

export function useDataset() {
  const { selectedId, getSelected, setSelected, datasets } = useDatasetStore()
  const selected = getSelected()

  const activeDataset: DatasetInfo | null = selected
    ? {
        file_id: selected.file_id ?? selectedId ?? '',
        filename: selected.filename ?? '',
        original_filename: selected.original_filename ?? selected.filename ?? '',
        total_rows: selected.total_rows,
        total_columns: selected.total_columns,
        quality_score: selected.quality_score,
        dataset_type: selected.dataset_type,
        status: selected.status,
      }
    : null

  const setActiveDataset = (ds: DatasetInfo | null) => {
    setSelected(ds?.file_id ?? null)
  }

  return { activeDataset, setActiveDataset, datasets }
}
