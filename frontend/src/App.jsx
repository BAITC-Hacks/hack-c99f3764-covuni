import React, { useState, useEffect } from 'react';

export default function App() {
  const [health, setHealth] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [customJson, setCustomJson] = useState('');
  const [uploadStatus, setUploadStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    setLoading(true);
    try {
      const [healthRes, profRes, evRes] = await Promise.all([
        fetch('/health'),
        fetch('/api/profiles'),
        fetch('/api/events'),
      ]);
      if (healthRes.ok) setHealth(await healthRes.json());
      if (profRes.ok) {
        const data = await profRes.json();
        setProfiles(data);
        if (data.length > 0) setSelectedProfile(data[0]);
      }
      if (evRes.ok) setEvents(await evRes.json());
    } catch (err) {
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadCustomProfiles = async () => {
    try {
      setUploadStatus({ type: 'info', message: 'Отправка профилей...' });
      const parsed = JSON.parse(customJson);
      const payload = {
        profiles: Array.isArray(parsed) ? parsed : [parsed],
      };

      const res = await fetch('/api/profiles/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const result = await res.json();
      if (res.ok) {
        setUploadStatus({
          type: 'success',
          message: `Успешно загружено ${result.loaded_count} проверочных профилей!`,
        });
        fetchInitialData();
      } else {
        setUploadStatus({
          type: 'error',
          message: `Ошибка валидации: ${result.validation_errors?.join(', ') || result.detail}`,
        });
      }
    } catch (err) {
      setUploadStatus({
        type: 'error',
        message: 'Невалидный JSON формат: ' + err.message,
      });
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation */}
      <header
        style={{
          background: 'linear-gradient(135deg, #007D43 0%, #004D28 100%)',
          color: '#ffffff',
          padding: '1.25rem 2rem',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        }}
      >
        <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '1.75rem' }}>🏦</span>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.025em' }}>
                Halyk Career Quest <span style={{ opacity: 0.8, fontSize: '1rem', fontWeight: 400 }}>| Team 202453</span>
              </h1>
            </div>
            <p style={{ fontSize: '0.875rem', opacity: 0.9, marginTop: '0.25rem' }}>
              Explainable Multi-factor AI Recommendation Engine (HackAlem AI)
            </p>
          </div>

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.15)',
                padding: '0.5rem 1rem',
                borderRadius: '8px',
                fontSize: '0.85rem',
                backdropFilter: 'blur(8px)',
              }}
            >
              Status:{' '}
              <strong style={{ color: health?.status === 'healthy' ? '#4ADE80' : '#F87171' }}>
                {health?.status || 'connecting...'}
              </strong>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main style={{ maxWidth: '1400px', margin: '2rem auto', padding: '0 1.5rem', flex: 1, width: '100%' }}>
        {/* Jury Verification Banner */}
        <section
          style={{
            background: '#FFFFFF',
            border: '2px dashed #007D43',
            borderRadius: '12px',
            padding: '1.5rem',
            marginBottom: '2rem',
            boxShadow: '0 4px 12px rgba(0, 125, 67, 0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ background: '#007D43', color: '#fff', padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600 }}>
                  JURY TESTING SUITE
                </span>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Загрузка проверочных профилей жюри</h2>
              </div>
              <p style={{ color: '#64748B', fontSize: '0.875rem', marginTop: '0.5rem', maxWidth: '800px' }}>
                Тестирование многофакторного скоринга на краевых кейсах: проверка устойчивости к нехватке ключевых грейдовых компетенций, учету усталости от обучения и истории участия.
              </p>
            </div>
          </div>

          <div style={{ marginTop: '1rem' }}>
            <textarea
              rows={4}
              value={customJson}
              onChange={(e) => setCustomJson(e.target.value)}
              placeholder='[{"id": "test_emp_999", "name": "Тестовый Сотрудник", "current_role": "Backend Developer", "current_grade": "Middle", "target_grade": "Senior", "skills": {"Python": 4, "Kubernetes": 1, "System Design": 2}}]'
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid #CBD5E1',
                fontFamily: 'monospace',
                fontSize: '0.85rem',
                backgroundColor: '#F8FAFC',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem' }}>
              <button
                onClick={handleUploadCustomProfiles}
                style={{
                  backgroundColor: '#007D43',
                  color: '#FFFFFF',
                  border: 'none',
                  padding: '0.6rem 1.5rem',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                }}
              >
                Загрузить в память (Без перезагрузки)
              </button>
              {uploadStatus && (
                <span
                  style={{
                    fontSize: '0.875rem',
                    color: uploadStatus.type === 'success' ? '#16A34A' : uploadStatus.type === 'error' ? '#DC2626' : '#2563EB',
                    fontWeight: 500,
                  }}
                >
                  {uploadStatus.message}
                </span>
              )}
            </div>
          </div>
        </section>

        {/* Dashboard Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '2rem' }}>
          {/* Left Column: Profiles List */}
          <section style={{ background: '#FFFFFF', borderRadius: '12px', padding: '1.5rem', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', justifyContent: 'space-between' }}>
              <span>Сотрудники ({profiles.length})</span>
              <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 400 }}>
                {profiles.filter((p) => p.is_custom).length} кастомных
              </span>
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '500px', overflowY: 'auto' }}>
              {profiles.map((p) => (
                <div
                  key={p.id}
                  onClick={() => setSelectedProfile(p)}
                  style={{
                    padding: '0.75rem 1rem',
                    borderRadius: '8px',
                    border: selectedProfile?.id === p.id ? '2px solid #007D43' : '1px solid #E2E8F0',
                    backgroundColor: selectedProfile?.id === p.id ? '#E6F5ED' : '#FFFFFF',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ fontSize: '0.95rem' }}>{p.name}</strong>
                    {p.is_custom && (
                      <span style={{ background: '#FEF3C7', color: '#92400E', fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: '4px', fontWeight: 600 }}>
                        Jury Custom
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#64748B', marginTop: '0.25rem' }}>
                    {p.current_role} • {p.current_grade} → <strong style={{ color: '#007D43' }}>{p.target_grade}</strong>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Right Column: Selected Profile Details & Event Recommendations */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {selectedProfile && (
              <div style={{ background: '#FFFFFF', borderRadius: '12px', padding: '1.5rem', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700 }}>{selectedProfile.name}</h3>
                    <p style={{ color: '#64748B', fontSize: '0.9rem' }}>
                      {selectedProfile.department || 'Департамент IT'} • {selectedProfile.current_role}
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ background: '#007D43', color: '#fff', padding: '0.3rem 0.8rem', borderRadius: '20px', fontSize: '0.85rem', fontWeight: 600 }}>
                      Цель: {selectedProfile.target_grade}
                    </span>
                  </div>
                </div>

                {/* Current Skills Radar / Badges */}
                <div style={{ marginTop: '1.25rem' }}>
                  <h4 style={{ fontSize: '0.9rem', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
                    Текущие компетенции:
                  </h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {Object.entries(selectedProfile.skills || {}).map(([skill, level]) => (
                      <span
                        key={skill}
                        style={{
                          background: '#F1F5F9',
                          border: '1px solid #CBD5E1',
                          padding: '0.3rem 0.6rem',
                          borderRadius: '6px',
                          fontSize: '0.85rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.4rem',
                        }}
                      >
                        <strong>{skill}</strong>
                        <span style={{ background: '#007D43', color: '#fff', borderRadius: '50%', width: '18px', height: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem' }}>
                          {level}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Upskilling Events Catalog */}
            <div style={{ background: '#FFFFFF', borderRadius: '12px', padding: '1.5rem', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
                Доступные события и тренинги ({events.length})
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {events.map((ev) => (
                  <div
                    key={ev.id}
                    style={{
                      border: '1px solid #E2E8F0',
                      borderRadius: '8px',
                      padding: '1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: '1rem', color: '#0F172A' }}>{ev.title}</strong>
                      <p style={{ fontSize: '0.85rem', color: '#64748B', marginTop: '0.2rem' }}>
                        {ev.description || 'Интенсивная программа развития'}
                      </p>
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                        <span style={{ background: '#E2E8F0', fontSize: '0.75rem', padding: '0.1rem 0.5rem', borderRadius: '4px' }}>
                          {ev.format}
                        </span>
                        <span style={{ background: '#E2E8F0', fontSize: '0.75rem', padding: '0.1rem 0.5rem', borderRadius: '4px' }}>
                          +{ev.skill_gain} skill level
                        </span>
                        {ev.target_skills?.map((sk) => (
                          <span key={sk} style={{ background: '#E6F5ED', color: '#007D43', fontSize: '0.75rem', padding: '0.1rem 0.5rem', borderRadius: '4px', fontWeight: 500 }}>
                            {sk}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer style={{ background: '#0F172A', color: '#94A3B8', padding: '1.5rem 2rem', textAlign: 'center', fontSize: '0.85rem', marginTop: '3rem' }}>
        HackAlem AI • Track: Halyk Bank (Career Quest) • Team 202453
      </footer>
    </div>
  );
}
