import React, { useState, useEffect, useMemo } from 'react';
import { X } from 'lucide-react';
import { Language, ScholarshipListItem, ScholarshipTag } from '../types';
import { translations } from '../App';

interface MetadataSchema {
  identity: string[];
  education_system: string[];
  tags: string[];
}

interface ScholarshipFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectScholarship: (tag: ScholarshipTag) => void;
  selectedTags: ScholarshipTag[];
  language: Language;
}

const MAX_TAGS = 3;
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Module-level cache to persist data across modal opens during the same session
let cachedScholarships: ScholarshipListItem[] | null = null;
let cachedSchema: MetadataSchema | null = null;

export const ScholarshipFilterModal: React.FC<ScholarshipFilterModalProps> = ({
  isOpen,
  onClose,
  onSelectScholarship,
  selectedTags,
  language,
}) => {
  const t = translations[language];
  const [scholarships, setScholarships] = useState<ScholarshipListItem[]>([]);
  const [schema, setSchema] = useState<MetadataSchema | null>(null);
  const [loading, setLoading] = useState(false);

  // Filter states
  const [filterCategory, setFilterCategory] = useState('');
  const [filterTag, setFilterTag] = useState('');

  // Extract unique categories dynamically from fetched scholarships
  const uniqueCategories = useMemo(() => {
    const cats = new Set(scholarships.map(s => s.category).filter(Boolean));
    return Array.from(cats).sort();
  }, [scholarships]);

  // Load data when modal opens
  useEffect(() => {
    if (!isOpen) return;

    const loadData = async () => {
      if (cachedScholarships && cachedSchema) {
        setScholarships(cachedScholarships);
        setSchema(cachedSchema);
        return;
      }

      setLoading(true);
      try {
        const [schRes, schemaRes] = await Promise.all([
          fetch(`${API_BASE_URL}/scholarships/filter`),
          fetch(`${API_BASE_URL}/metadata_schema.json`),
        ]);
        const schData = await schRes.json();
        const schemaData = await schemaRes.json();
        if (schData.status === 'success') {
          cachedScholarships = schData.data;
          setScholarships(schData.data);
        }
        cachedSchema = schemaData;
        setSchema(schemaData);
      } catch (err) {
        console.error('Failed to load filter data:', err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [isOpen]);

  // Reset filters when modal opens
  useEffect(() => {
    if (isOpen) {
      setFilterCategory('');
      setFilterTag('');
    }
  }, [isOpen]);

  // Client-side filtering
  const filteredScholarships = useMemo(() => {
    return scholarships.filter((s) => {
      if (filterCategory && s.category !== filterCategory) return false;
      if (filterTag && !s.tags.includes(filterTag)) return false;
      return true;
    });
  }, [scholarships, filterCategory, filterTag]);

  const isMaxTags = selectedTags.length >= MAX_TAGS;
  const selectedCodes = new Set(selectedTags.map((t) => t.scholarship_code));

  const handleCardClick = (item: ScholarshipListItem) => {
    if (isMaxTags || selectedCodes.has(item.scholarship_code)) return;
    onSelectScholarship({
      title: item.title,
      scholarship_code: item.scholarship_code,
    });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="filter-backdrop" onClick={onClose} />
      <div className="filter-modal" role="dialog" aria-modal="true">
        {/* Header */}
        <div className="filter-modal-header">
          <h3>{t.filter_title || '獎學金篩選'}</h3>
          <button className="filter-modal-close" onClick={onClose} title="Close">
            <X size={20} />
          </button>
        </div>

        {/* Dropdown Filters */}
        <div className="filter-dropdown-row">
          <div className="filter-dropdown-group">
            <label>{/* i18n label could be added here, fallback to 類別 */ t.filter_category || '類別'}</label>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
            >
              <option value="">{t.filter_all || '全部'}</option>
              {uniqueCategories.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div className="filter-dropdown-group">
            <label>{t.filter_tags || '條件'}</label>
            <select
              value={filterTag}
              onChange={(e) => setFilterTag(e.target.value)}
            >
              <option value="">{t.filter_all || '全部'}</option>
              {schema?.tags.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Results */}
        <div className="filter-results-header">
          {t.filter_results || '篩選結果'}
          <span className="filter-results-count">
            （{filteredScholarships.length} {t.filter_results_unit || '筆'}）
          </span>
          {isMaxTags && (
            <span className="filter-max-hint">
              {t.filter_max_hint || '已達上限 3 個'}
            </span>
          )}
        </div>

        <div className="filter-results-list">
          {loading ? (
            <div className="filter-loading">{t.filter_loading || '載入中...'}</div>
          ) : filteredScholarships.length === 0 ? (
            <div className="filter-empty">{t.filter_empty || '沒有符合的結果'}</div>
          ) : (
            filteredScholarships.map((item) => {
              const isSelected = selectedCodes.has(item.scholarship_code);
              const isDisabled = isMaxTags && !isSelected;
              return (
                <div
                  key={item.scholarship_code}
                  className={`filter-card ${isSelected ? 'filter-card-selected' : ''} ${isDisabled ? 'filter-card-disabled' : ''}`}
                  onClick={() => handleCardClick(item)}
                  title={isDisabled ? (t.filter_max_hint || '已達上限 3 個') : item.title}
                >
                  <span className="filter-card-icon">🎓</span>
                  <span className="filter-card-title">{item.title}</span>
                  {isSelected && <span className="filter-card-check">✓</span>}
                </div>
              );
            })
          )}
        </div>
      </div>
    </>
  );
};
