import { useState, useEffect } from 'react';
import { 
  Stethoscope, 
  Sparkles, 
  FlaskConical, 
  Scan, 
  CheckCircle2, 
  Clock, 
  AlertTriangle, 
  Plus, 
  Search,
  Eye,
  Check,
  X,
  Info,
  Calendar
} from 'lucide-react';
import { api } from '../services/api';
import type { 
  HealthPackage, 
  ImagingServiceCategory, 
  OrderedPackageRecord, 
  LabReportRecord,
  OrderStatus 
} from '../types/medtwin';

interface ClinicalCatalogPanelProps {
  caseId: string | null;
  orders: OrderedPackageRecord[];
  labReports: LabReportRecord[];
  onRefreshData: () => void;
  loading: boolean;
}

export const ClinicalCatalogPanel: React.FC<ClinicalCatalogPanelProps> = ({
  caseId,
  orders,
  labReports,
  onRefreshData,
  loading: parentLoading
}) => {
  const [activeTab, setActiveTab] = useState<'PACKAGES' | 'IMAGING' | 'ORDERS' | 'LAB_REPORTS'>('PACKAGES');
  const [packages, setPackages] = useState<HealthPackage[]>([]);
  const [imagingServices, setImagingServices] = useState<ImagingServiceCategory[]>([]);
  const [catalogLoading, setCatalogLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>('');
  
  // Ordering Modal / Inline state
  const [selectedItemToOrder, setSelectedItemToOrder] = useState<{ id: string; name: string; category: string } | null>(null);
  const [orderNotes, setOrderNotes] = useState<string>('');
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  // Lab Report Modal state
  const [isLabModalOpen, setIsLabModalOpen] = useState<boolean>(false);
  const [selectedOrderForLab, setSelectedOrderForLab] = useState<OrderedPackageRecord | null>(null);
  const [labPatientSex, setLabPatientSex] = useState<'M' | 'F'>('M');
  const [labFacilityName, setLabFacilityName] = useState<string>('MedTwin Central Laboratory');
  const [labTestEntries, setLabTestEntries] = useState<{ code: string; name: string; value: string; unit: string }[]>([]);
  const [selectedReportToView, setSelectedReportToView] = useState<LabReportRecord | null>(null);

  // Load Catalog items
  useEffect(() => {
    let isMounted = true;
    const fetchCatalog = async () => {
      try {
        const [pkgs, imaging] = await Promise.all([
          api.getHealthPackages().catch(() => []),
          api.getImagingServices().catch(() => []),
        ]);
        if (isMounted) {
          setPackages(pkgs);
          setImagingServices(imaging);
        }
      } catch (err) {
        console.error('Failed to load clinical catalog:', err);
      } finally {
        if (isMounted) setCatalogLoading(false);
      }
    };
    void fetchCatalog();
    return () => { isMounted = false; };
  }, []);

  // Handle Order Creation
  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseId || !selectedItemToOrder) return;
    setActionLoading(true);
    try {
      await api.createCaseOrder(caseId, selectedItemToOrder.id, orderNotes.trim() || undefined);
      setSelectedItemToOrder(null);
      setOrderNotes('');
      onRefreshData();
      setActiveTab('ORDERS');
    } catch (err) {
      alert(`Order placement failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Order Status Update
  const handleUpdateStatus = async (orderId: number, newStatus: OrderStatus) => {
    if (!caseId) return;
    setActionLoading(true);
    try {
      await api.updateCaseOrderStatus(caseId, orderId, newStatus);
      onRefreshData();
    } catch (err) {
      alert(`Status update failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setActionLoading(false);
    }
  };

  // Prepare Lab Report Entry Form for an Order
  const handleOpenLabEntry = async (order: OrderedPackageRecord) => {
    setSelectedOrderForLab(order);
    setActionLoading(true);
    try {
      const detailedPkg = await api.getHealthPackage(order.package_id);
      const labCatalog = await api.getLabTestCatalog();
      
      const codes = detailedPkg.lab_test_codes || [];
      const testMap = new Map(labCatalog.tests.map(t => [t.code, t]));
      
      const initialEntries = codes.map(c => {
        const ref = testMap.get(c);
        let defaultVal = '';
        // Provide typical default or placeholder
        if (c === 'HB') defaultVal = '13.8';
        else if (c === 'PCV') defaultVal = '42.5';
        else if (c === 'RBC') defaultVal = '4.85';
        else if (c === 'TLC') defaultVal = '7.2';
        else if (c === 'PLT') defaultVal = '250';
        else if (c === 'FBS') defaultVal = '92';
        else if (c === 'PPBS') defaultVal = '126';
        else if (c === 'HBA1C') defaultVal = '5.4';
        else if (c === 'TC') defaultVal = '185';
        else if (c === 'TG') defaultVal = '130';
        else if (c === 'HDL') defaultVal = '50';
        else if (c === 'LDL') defaultVal = '105';
        else if (c === 'VLDL') defaultVal = '26';
        else if (c === 'UREA') defaultVal = '24.0';
        else if (c === 'CREAT') defaultVal = '0.95';
        else if (c === 'URIC') defaultVal = '5.1';
        else if (c === 'BLOOD_GROUP') defaultVal = 'O+';
        else if (c === 'NA') defaultVal = '139';
        else if (c === 'K') defaultVal = '4.2';
        else if (c === 'CA') defaultVal = '9.4';
        else if (c === 'PHOS') defaultVal = '3.5';
        else if (c === 'HCO3') defaultVal = '25.0';
        else if (c === 'TSH') defaultVal = '2.1';
        else if (c === 'VITD') defaultVal = '38.0';
        else if (c === 'B12') defaultVal = '420';
        else if (c === 'IRON') defaultVal = '95';
        else if (c === 'TIBC') defaultVal = '320';
        else if (c === 'PTH') defaultVal = '35.0';
        else if (c === 'HBSAG' || c === 'HCV_AB' || c === 'HIV_AB_AG') defaultVal = 'NON_REACTIVE';
        else if (c === 'MP' || c === 'OCCULT_BLOOD') defaultVal = 'NEGATIVE';
        else if (c.startsWith('URINE_') && (c.includes('PROTEIN') || c.includes('GLUCOSE'))) defaultVal = 'NIL';
        else if (c === 'URINE_PH') defaultVal = '6.0';
        else if (c === 'URINE_SG') defaultVal = '1.020';
        else if (c === 'URINE_PUS') defaultVal = '2';
        else if (c === 'URINE_RBC') defaultVal = '0';
        else if (c === 'AFP') defaultVal = '3.2';
        else if (c === 'PSA') defaultVal = '1.1';
        else defaultVal = ref?.kind === 'QUANTITATIVE' ? '1.0' : (ref?.expected || 'NORMAL');

        return {
          code: c,
          name: ref?.name || c,
          unit: ref?.unit || '',
          value: defaultVal
        };
      });

      setLabTestEntries(initialEntries);
      setIsLabModalOpen(true);
    } catch (err) {
      alert(`Could not initialize lab entry: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setActionLoading(false);
    }
  };

  // Submit Laboratory Results
  const handleSubmitLabReport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseId || !selectedOrderForLab) return;
    setActionLoading(true);
    try {
      const resultsPayload = labTestEntries.map(e => ({
        code: e.code,
        value: isNaN(Number(e.value)) || e.value === '' ? e.value : Number(e.value)
      }));

      await api.createCaseLabReport(caseId, {
        ordered_package_id: selectedOrderForLab.id,
        report_title: selectedOrderForLab.package_name,
        lab_name: labFacilityName,
        sample_type: 'Whole Blood EDTA / Serum',
        patient_sex: labPatientSex,
        clinical_summary: `Structured diagnostic investigation for ${selectedOrderForLab.package_name}.`,
        results: resultsPayload
      });

      // Update order to completed if not yet
      if (selectedOrderForLab.status !== 'COMPLETED') {
        await api.updateCaseOrderStatus(caseId, selectedOrderForLab.id, 'COMPLETED').catch(() => null);
      }

      setIsLabModalOpen(false);
      setSelectedOrderForLab(null);
      onRefreshData();
      setActiveTab('LAB_REPORTS');
    } catch (err) {
      alert(`Failed to record lab report: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setActionLoading(false);
    }
  };

  // Filter packages based on search term
  const filteredPackages = packages.filter(p => 
    p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.components.some(c => c.name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="panel-card" style={{ marginBottom: '1.75rem', position: 'relative' }}>
      {/* Header with Title & Navigation Tabs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div style={{ padding: '0.45rem', borderRadius: '10px', background: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.25)', color: 'var(--accent-cyan)' }}>
              <Stethoscope size={20} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'white', margin: 0 }}>
                  Clinical Health Packages & Diagnostic Imaging
                </h3>
                <span className="badge badge-cyan" style={{ fontSize: '0.65rem' }}>
                  Institutional Service Catalog
                </span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '0.2rem 0 0' }}>
                Standardized health check-up packages, targeted organ top-ups, advanced multi-slice CT, ultrasound, and angiography protocols.
              </p>
            </div>
          </div>
        </div>

        {/* Tab Controls */}
        <div style={{ display: 'flex', gap: '0.4rem', background: 'rgba(3, 7, 18, 0.6)', padding: '0.3rem', borderRadius: '0.85rem', border: '1px solid var(--border-subtle)' }}>
          <button
            type="button"
            onClick={() => setActiveTab('PACKAGES')}
            className={`btn-sm ${activeTab === 'PACKAGES' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '0.6rem' }}
          >
            <Sparkles size={13} />
            <span>Health Packages ({packages.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('IMAGING')}
            className={`btn-sm ${activeTab === 'IMAGING' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '0.6rem' }}
          >
            <Scan size={13} />
            <span>Diagnostic Imaging</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('ORDERS')}
            className={`btn-sm ${activeTab === 'ORDERS' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '0.6rem', position: 'relative' }}
          >
            <Clock size={13} />
            <span>Case Orders ({orders.length})</span>
            {orders.some(o => o.status === 'ORDERED') && (
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#f59e0b', marginLeft: '4px' }} />
            )}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('LAB_REPORTS')}
            className={`btn-sm ${activeTab === 'LAB_REPORTS' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '0.6rem' }}
          >
            <FlaskConical size={13} />
            <span>Lab Reports ({labReports.length})</span>
          </button>
        </div>
      </div>

      {/* Mandatory Notice */}
      <div className="alert-notice" style={{ marginBottom: '1.25rem', padding: '0.65rem 1rem' }}>
        <Info size={15} style={{ color: '#fbbf24', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>Standard Clinical Diagnostic Ordering:</strong> Diagnostic packages and imaging procedures 
          ordered for digital twin cases are structured into longitudinal record streams. Laboratory values are automatically 
          evaluated against standard biological reference intervals. Diagnostic conclusions require human clinician validation.
        </div>
      </div>

      {catalogLoading ? (
        <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Loading diagnostic catalog protocols...
        </div>
      ) : null}

      {/* ----------------- TAB 1: HEALTH PACKAGES ----------------- */}
      {!catalogLoading && activeTab === 'PACKAGES' && (
        <div>
          {/* Search Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', maxWidth: '400px' }}>
            <div style={{ position: 'relative', width: '100%' }}>
              <Search size={14} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Search package or test component..."
                className="medtwin-input"
                style={{ paddingLeft: '2.2rem', height: '36px' }}
              />
            </div>
          </div>

          <div className="grid-2">
            {filteredPackages.map(pkg => (
              <div 
                key={pkg.id} 
                style={{ 
                  background: 'rgba(15, 23, 42, 0.85)', 
                  border: '1px solid var(--border-subtle)', 
                  borderRadius: '1rem', 
                  padding: '1.25rem', 
                  display: 'flex', 
                  flexDirection: 'column', 
                  justifyContent: 'space-between',
                  transition: 'all 0.2s ease',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.5rem' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.25rem' }}>
                        <span className={`badge ${pkg.kind === 'COMPREHENSIVE' ? 'badge-cyan' : 'badge-purple'}`} style={{ fontSize: '0.62rem' }}>
                          {pkg.kind === 'COMPREHENSIVE' ? 'Comprehensive Master' : 'Specialized Top-Up'}
                        </span>
                        <span className="badge badge-amber" style={{ fontSize: '0.62rem' }}>
                          {pkg.category}
                        </span>
                      </div>
                      <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'white', margin: 0 }}>
                        {pkg.name}
                      </h4>
                    </div>
                    <span style={{ fontSize: '0.68rem', fontFamily: 'monospace', color: 'var(--text-dim)', padding: '0.2rem 0.5rem', background: 'rgba(0,0,0,0.3)', borderRadius: '6px' }}>
                      {pkg.id}
                    </span>
                  </div>

                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.85rem' }}>
                    {pkg.description}
                  </p>

                  <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.75rem', marginBottom: '1rem' }}>
                    <span style={{ fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-dim)', fontWeight: 600 }}>
                      Package Details & Included Tests:
                    </span>
                    <ul style={{ listStyle: 'none', padding: 0, margin: '0.5rem 0 0', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      {pkg.components.map((comp, idx) => (
                        <li key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.73rem', background: 'rgba(3, 7, 18, 0.4)', padding: '0.35rem 0.65rem', borderRadius: '0.45rem' }}>
                          <span style={{ color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: comp.type === 'LAB' ? 'var(--accent-cyan)' : comp.type === 'IMAGING' ? 'var(--accent-emerald)' : comp.type === 'CARDIAC' ? 'var(--accent-rose)' : 'var(--accent-purple)' }} />
                            {comp.name}
                          </span>
                          <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)', background: 'rgba(255,255,255,0.04)', padding: '0.1rem 0.4rem', borderRadius: '4px' }}>
                            {comp.type}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    {pkg.components.length} components included
                  </span>
                  <button
                    type="button"
                    onClick={() => setSelectedItemToOrder({ id: pkg.id, name: pkg.name, category: pkg.category })}
                    className="btn-primary btn-sm"
                    disabled={!caseId || parentLoading || actionLoading}
                  >
                    <Plus size={13} />
                    <span>Order for Case</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ----------------- TAB 2: DIAGNOSTIC IMAGING ----------------- */}
      {!catalogLoading && activeTab === 'IMAGING' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {imagingServices.map(category => (
            <div 
              key={category.id} 
              style={{ 
                background: 'rgba(15, 23, 42, 0.85)', 
                border: '1px solid var(--border-subtle)', 
                borderRadius: '1.1rem', 
                padding: '1.25rem' 
              }}
            >
              <div style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{ padding: '0.35rem', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.3)', color: 'var(--accent-emerald)' }}>
                    <Scan size={16} />
                  </div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'white', margin: 0 }}>
                    {category.category}
                  </h4>
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '0.35rem 0 0', lineHeight: 1.5 }}>
                  {category.description}
                </p>
              </div>

              {/* Modalities Grid */}
              <div className="grid-2">
                {category.modalities.map(mod => (
                  <div 
                    key={mod.code} 
                    style={{ 
                      background: 'rgba(3, 7, 18, 0.6)', 
                      border: '1px solid rgba(255, 255, 255, 0.05)', 
                      borderRadius: '0.75rem', 
                      padding: '0.85rem 1rem',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between'
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'white' }}>
                          {mod.name}
                        </span>
                        <span style={{ fontSize: '0.65rem', fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
                          {mod.code}
                        </span>
                      </div>
                      {mod.details && (
                        <p style={{ fontSize: '0.72rem', color: 'var(--text-dim)', margin: '0 0 0.75rem', lineHeight: 1.4 }}>
                          Indications: {mod.details}
                        </p>
                      )}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                      <button
                        type="button"
                        onClick={() => setSelectedItemToOrder({ id: mod.code, name: mod.name, category: category.category })}
                        className="btn-secondary btn-sm"
                        disabled={!caseId || parentLoading || actionLoading}
                      >
                        <Plus size={12} />
                        <span>Order Study</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ----------------- TAB 3: CASE ORDERS ----------------- */}
      {!catalogLoading && activeTab === 'ORDERS' && (
        <div>
          {orders.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem 1rem', background: 'rgba(3, 7, 18, 0.4)', borderRadius: '1rem', border: '1px dashed var(--border-subtle)' }}>
              <Clock size={32} style={{ color: 'var(--text-dim)', margin: '0 auto 0.75rem' }} />
              <h4 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                No Diagnostic Studies Ordered Yet
              </h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', maxWidth: '350px', margin: '0 auto 1rem' }}>
                Select a Health Check-up Package or Diagnostic Imaging protocol from the catalog to order for this digital twin case.
              </p>
              <button
                type="button"
                onClick={() => setActiveTab('PACKAGES')}
                className="btn-primary btn-sm"
              >
                Browse Health Packages
              </button>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="medtwin-table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>Ordered Study / Package</th>
                    <th>Category</th>
                    <th>Ordered Date</th>
                    <th>Clinical Status</th>
                    <th>Notes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map(order => (
                    <tr key={order.id}>
                      <td style={{ fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
                        ORD-{order.id}
                      </td>
                      <td>
                        <span style={{ fontWeight: 600, color: 'white' }}>{order.package_name}</span>
                        <span style={{ display: 'block', fontSize: '0.65rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                          {order.package_id}
                        </span>
                      </td>
                      <td>
                        <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>
                          {order.category}
                        </span>
                      </td>
                      <td style={{ color: 'var(--text-muted)' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          <Calendar size={12} style={{ color: 'var(--text-dim)' }} />
                          {new Date(order.created_at).toLocaleDateString()}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${
                          order.status === 'COMPLETED' ? 'badge-emerald' :
                          order.status === 'IN_PROGRESS' ? 'badge-cyan' :
                          order.status === 'CANCELLED' ? 'badge-rose' : 'badge-amber'
                        }`}>
                          {order.status}
                        </span>
                      </td>
                      <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-dim)' }}>
                        {order.clinical_notes || '—'}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          {order.status === 'ORDERED' && (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(order.id, 'IN_PROGRESS')}
                              className="btn-secondary btn-sm"
                              disabled={actionLoading}
                            >
                              Start Processing
                            </button>
                          )}
                          {order.status === 'IN_PROGRESS' && (
                            <button
                              type="button"
                              onClick={() => handleUpdateStatus(order.id, 'COMPLETED')}
                              className="btn-secondary btn-sm"
                              style={{ color: 'var(--accent-emerald)', borderColor: 'rgba(16, 185, 129, 0.3)' }}
                              disabled={actionLoading}
                            >
                              <Check size={12} />
                              <span>Complete</span>
                            </button>
                          )}
                          {/* If it's a lab package, offer 1-click Enter Results */}
                          {order.package_id.startsWith('PKG-') && (
                            <button
                              type="button"
                              onClick={() => handleOpenLabEntry(order)}
                              className="btn-primary btn-sm"
                              style={{ fontSize: '0.7rem' }}
                              disabled={actionLoading}
                            >
                              <FlaskConical size={12} />
                              <span>Record Lab Data</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ----------------- TAB 4: LABORATORY REPORTS ----------------- */}
      {!catalogLoading && activeTab === 'LAB_REPORTS' && (
        <div>
          {labReports.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem 1rem', background: 'rgba(3, 7, 18, 0.4)', borderRadius: '1rem', border: '1px dashed var(--border-subtle)' }}>
              <FlaskConical size={32} style={{ color: 'var(--text-dim)', margin: '0 auto 0.75rem' }} />
              <h4 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                No Structured Lab Reports Recorded
              </h4>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', maxWidth: '400px', margin: '0 auto 1rem' }}>
                Order a Health Check-up Package (e.g. General Health, Well Women, Renal, Digestive, or Liver) and click "Record Lab Data" to log structured biomarker panels.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {labReports.map(report => (
                <div 
                  key={report.id} 
                  style={{ 
                    background: 'rgba(15, 23, 42, 0.85)', 
                    border: '1px solid var(--border-subtle)', 
                    borderRadius: '1rem', 
                    padding: '1.25rem' 
                  }}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <span className="badge badge-cyan" style={{ fontSize: '0.65rem' }}>
                          LAB REPORT #{report.id}
                        </span>
                        <span className="badge badge-emerald" style={{ fontSize: '0.65rem' }}>
                          {report.sample_type}
                        </span>
                        <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>
                          Sex: {report.patient_sex || 'Unspecified'}
                        </span>
                      </div>
                      <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'white', margin: 0 }}>
                        {report.report_title}
                      </h4>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        Facility: {report.lab_name} • Recorded: {new Date(report.created_at).toLocaleString()}
                      </span>
                    </div>

                    {/* Flag summary chips */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      {report.flag_counts['NORMAL'] && (
                        <span className="badge badge-emerald" style={{ fontSize: '0.68rem' }}>
                          <CheckCircle2 size={11} /> {report.flag_counts['NORMAL']} Normal
                        </span>
                      )}
                      {report.flag_counts['HIGH'] && (
                        <span className="badge badge-rose" style={{ fontSize: '0.68rem' }}>
                          <AlertTriangle size={11} /> {report.flag_counts['HIGH']} Elevated (High)
                        </span>
                      )}
                      {report.flag_counts['LOW'] && (
                        <span className="badge badge-amber" style={{ fontSize: '0.68rem' }}>
                          <AlertTriangle size={11} /> {report.flag_counts['LOW']} Low
                        </span>
                      )}
                      {report.flag_counts['ABNORMAL'] && (
                        <span className="badge badge-rose" style={{ fontSize: '0.68rem' }}>
                          <AlertTriangle size={11} /> {report.flag_counts['ABNORMAL']} Abnormal
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => setSelectedReportToView(selectedReportToView?.id === report.id ? null : report)}
                        className="btn-secondary btn-sm"
                        style={{ marginLeft: '0.5rem' }}
                      >
                        <Eye size={12} />
                        <span>{selectedReportToView?.id === report.id ? 'Collapse' : 'View Full Panel'}</span>
                      </button>
                    </div>
                  </div>

                  {/* Biomarkers Table */}
                  <div style={{ overflowX: 'auto' }}>
                    <table className="medtwin-table">
                      <thead>
                        <tr>
                          <th>Biomarker / Test Name</th>
                          <th>Measured Value</th>
                          <th>Unit</th>
                          <th>Biological Reference Interval</th>
                          <th>Organ System</th>
                          <th>Status / Flag</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.results.slice(0, selectedReportToView?.id === report.id ? undefined : 6).map((res, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 600, color: 'white' }}>
                              {res.test_name}
                              <span style={{ display: 'block', fontSize: '0.65rem', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                                Code: {res.code}
                              </span>
                            </td>
                            <td style={{ fontSize: '0.9rem', fontWeight: 700, color: res.status === 'HIGH' ? '#fb7185' : res.status === 'LOW' ? '#fbbf24' : res.status === 'ABNORMAL' ? '#fb7185' : 'white' }}>
                              {res.result_value}
                            </td>
                            <td style={{ color: 'var(--text-muted)' }}>{res.unit || '—'}</td>
                            <td style={{ color: 'var(--text-dim)', fontFamily: 'monospace' }}>{res.bio_ref_interval || '—'}</td>
                            <td>
                              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                {res.organ_system}
                              </span>
                            </td>
                            <td>
                              <span className={`badge ${
                                res.status === 'NORMAL' ? 'badge-emerald' :
                                res.status === 'HIGH' ? 'badge-rose' :
                                res.status === 'LOW' ? 'badge-amber' :
                                res.status === 'ABNORMAL' ? 'badge-rose' : 'badge-purple'
                              }`}>
                                {res.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {selectedReportToView?.id !== report.id && report.results.length > 6 && (
                    <div style={{ textAlign: 'center', marginTop: '0.75rem' }}>
                      <button
                        type="button"
                        onClick={() => setSelectedReportToView(report)}
                        style={{ background: 'none', border: 'none', color: 'var(--accent-cyan)', fontSize: '0.75rem', cursor: 'pointer', fontWeight: 600 }}
                      >
                        + Show all {report.results.length} biomarkers in this panel
                      </button>
                    </div>
                  )}

                  {report.clinical_summary && (
                    <div style={{ marginTop: '0.85rem', padding: '0.65rem 0.85rem', background: 'rgba(3, 7, 18, 0.4)', borderRadius: '0.6rem', border: '1px solid rgba(255,255,255,0.04)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <strong style={{ color: 'white' }}>Clinical Summary: </strong>
                      {report.clinical_summary}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ----------------- MODAL: ORDER CONFIRMATION ----------------- */}
      {selectedItemToOrder && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '1rem' }}>
          <div style={{ background: '#090e1a', border: '1px solid var(--border-subtle)', borderRadius: '1.25rem', padding: '1.5rem', maxWidth: '480px', width: '100%', boxShadow: '0 20px 40px rgba(0,0,0,0.6)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Plus size={18} style={{ color: 'var(--accent-cyan)' }} />
                <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'white', margin: 0 }}>
                  Order Diagnostic Service
                </h4>
              </div>
              <button
                type="button"
                onClick={() => setSelectedItemToOrder(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handlePlaceOrder}>
              <div style={{ marginBottom: '1rem', background: 'rgba(15, 23, 42, 0.7)', padding: '0.85rem', borderRadius: '0.75rem', border: '1px solid rgba(255,255,255,0.06)' }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', textTransform: 'uppercase' }}>Selected Study:</span>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'white', marginTop: '0.15rem' }}>
                  {selectedItemToOrder.name}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem' }}>
                  <span className="badge badge-purple" style={{ fontSize: '0.65rem' }}>{selectedItemToOrder.category}</span>
                  <span className="badge badge-cyan" style={{ fontSize: '0.65rem', fontFamily: 'monospace' }}>{selectedItemToOrder.id}</span>
                </div>
              </div>

              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.35rem', fontWeight: 600 }}>
                  Clinical Indication / Special Instructions (Optional):
                </label>
                <textarea
                  value={orderNotes}
                  onChange={e => setOrderNotes(e.target.value)}
                  placeholder="e.g. Routine annual health audit, baseline cardiovascular risk assessment, pre-op clearance."
                  className="medtwin-textarea"
                  rows={3}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setSelectedItemToOrder(null)}
                  className="btn-secondary btn-sm"
                  disabled={actionLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary btn-sm"
                  disabled={actionLoading}
                >
                  {actionLoading ? 'Ordering...' : 'Confirm Order'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ----------------- MODAL: RECORD LAB REPORT ----------------- */}
      {isLabModalOpen && selectedOrderForLab && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '1rem' }}>
          <div style={{ background: '#090e1a', border: '1px solid var(--border-subtle)', borderRadius: '1.25rem', padding: '1.5rem', maxWidth: '720px', width: '100%', maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 20px 40px rgba(0,0,0,0.6)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <FlaskConical size={18} style={{ color: 'var(--accent-cyan)' }} />
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'white', margin: 0 }}>
                    Record Laboratory Results
                  </h4>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    {selectedOrderForLab.package_name} ({selectedOrderForLab.package_id})
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsLabModalOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmitLabReport}>
              <div className="grid-2" style={{ marginBottom: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                    Reporting Laboratory:
                  </label>
                  <input
                    type="text"
                    value={labFacilityName}
                    onChange={e => setLabFacilityName(e.target.value)}
                    className="medtwin-input"
                    required
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                    Patient Biological Sex (for reference intervals):
                  </label>
                  <select
                    value={labPatientSex}
                    onChange={e => setLabPatientSex(e.target.value as 'M' | 'F')}
                    className="medtwin-select"
                  >
                    <option value="M">Male (M)</option>
                    <option value="F">Female (F)</option>
                  </select>
                </div>
              </div>

              <div style={{ marginBottom: '1rem' }}>
                <span style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'white', marginBottom: '0.5rem' }}>
                  Biomarker Values ({labTestEntries.length} tests):
                </span>
                <div style={{ maxHeight: '350px', overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: '0.75rem', padding: '0.5rem', background: 'rgba(3, 7, 18, 0.5)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.65rem' }}>
                    {labTestEntries.map((entry, idx) => (
                      <div key={entry.code} style={{ background: 'rgba(15, 23, 42, 0.7)', padding: '0.5rem 0.75rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.04)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'white', fontWeight: 600, marginBottom: '0.25rem' }}>
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.name}</span>
                          <span style={{ color: 'var(--text-dim)', fontSize: '0.65rem', fontFamily: 'monospace' }}>{entry.code}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <input
                            type="text"
                            value={entry.value}
                            onChange={e => {
                              const newEntries = [...labTestEntries];
                              newEntries[idx].value = e.target.value;
                              setLabTestEntries(newEntries);
                            }}
                            className="medtwin-input"
                            style={{ height: '32px', fontSize: '0.8rem', fontWeight: 600 }}
                            required
                          />
                          {entry.unit && (
                            <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                              {entry.unit}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
                <button
                  type="button"
                  onClick={() => setIsLabModalOpen(false)}
                  className="btn-secondary btn-sm"
                  disabled={actionLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary btn-sm"
                  disabled={actionLoading}
                >
                  {actionLoading ? 'Recording & Evaluating...' : 'Submit & Flag Results'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
