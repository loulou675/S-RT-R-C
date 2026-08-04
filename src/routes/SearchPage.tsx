import { ArrowRight, Camera, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFlow } from '../app/useFlow'
import { ItemGlyph } from '../components/ItemGlyph'
import { commonSearchItems, searchWasteItems } from '../features/search/searchEngine'
import { hasConditionQuestion } from '../features/sorting/ruleEngine'

export function SearchPage() {
  const navigate = useNavigate()
  const { setConfirmedItem } = useFlow()
  const [query, setQuery] = useState('')
  const results = useMemo(() => searchWasteItems(query), [query])

  function choose(itemCode: string) {
    setConfirmedItem(itemCode)
    if (hasConditionQuestion(itemCode)) {
      navigate(`/condition?item=${itemCode}`)
    } else {
      navigate(`/result?item=${itemCode}&condition=default`)
    }
  }

  return (
    <section className="flow-layout search-page">
      <div className="page-heading">
        <p className="eyebrow">Manual search</p>
        <h1>Find the item in the waste database.</h1>
      </div>

      <label className="manual-search">
        <Search size={18} aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search for an item, e.g. plastic cup, battery, pizza box"
          autoFocus
        />
      </label>

      {!query ? (
        <div className="common-grid">
          {commonSearchItems().map((label) => (
            <button type="button" key={label} onClick={() => setQuery(label)}>
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {query && !results.length ? (
        <div className="empty-search">
          <h2>We could not find this item in the current database.</h2>
          <div className="button-row full">
            <button type="button" className="secondary-action" onClick={() => setQuery('')}>
              Try another name
            </button>
            <button type="button" className="primary-action" onClick={() => navigate('/scan')}>
              <Camera size={17} aria-hidden="true" />
              Scan with camera
            </button>
            <button type="button" className="ghost-action" onClick={() => setQuery('plastic')}>
              Browse by material
            </button>
          </div>
        </div>
      ) : null}

      <div className="result-cards">
        {results.map(({ item, matchedBy }) => (
          <button type="button" key={item.code} className="search-result-card" onClick={() => choose(item.code)}>
            <ItemGlyph objectType={item.objectType} />
            <span>
              <strong>{item.nameEn}</strong>
              <small>
                {item.nameVi} · {item.primaryMaterialCode.replaceAll('_', ' ')} · matched {matchedBy}
              </small>
            </span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  )
}
