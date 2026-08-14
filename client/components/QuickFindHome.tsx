"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness, Check, MapPin, Save, Search, Upload } from "lucide-react";
import {
  applyResumeProfileSuggestions,
  createJobSearchCriterion,
  getAuthToken,
  importResumePdf,
  JobSearchCriterion,
  listJobSearchCriteria,
  listResumeProfiles,
  QuickFindCandidate,
  QuickFindResponse,
  quickFindJobs,
  ResumeImportResponse,
  ResumeProfile,
  retryResumeImport,
  saveQuickFindJobs,
} from "../lib/api";
import { DashboardHome } from "./DashboardHome";
import {
  AlertBanner,
  Button,
  EmptyState,
  MatchScoreBadge,
  PageHeader,
  SectionHeader,
  SkeletonRows,
  ToastRegion,
  Toolbar,
} from "./ui";

function recommendationKey(candidate: QuickFindCandidate): number {
  return candidate.jobs_cache_id;
}

function resumeSearchLabel(profile: ResumeProfile): string {
  const role = profile.resume_data.target_roles.find((item) => item.trim());
  if (role) return role;
  if (profile.resume_data.headline?.trim()) return profile.resume_data.headline.trim();
  return profile.resume_data.skills.filter((item) => item.trim()).slice(0, 3).join(" + ");
}

export function QuickFindHome() {
  if (!getAuthToken()) return <DashboardHome />;
  return <AuthenticatedQuickFindHome />;
}

function AuthenticatedQuickFindHome() {
  const [defaultResume, setDefaultResume] = useState<ResumeProfile | null>(null);
  const [searchCriteria, setSearchCriteria] = useState<JobSearchCriterion[]>([]);
  const [selectedCriterionId, setSelectedCriterionId] = useState<number | null>(null);
  const [resumeImport, setResumeImport] = useState<ResumeImportResponse | null>(null);
  const [keyword, setKeyword] = useState("");
  const [location, setLocation] = useState("");
  const [searchEditorOpen, setSearchEditorOpen] = useState(false);
  const [pendingCriterionSave, setPendingCriterionSave] = useState<{ keyword: string; location: string } | null>(null);
  const [recommendations, setRecommendations] = useState<QuickFindResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportingResume, setIsImportingResume] = useState(false);
  const [isApplyingResume, setIsApplyingResume] = useState(false);
  const [isFinding, setIsFinding] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const candidates = recommendations?.candidates ?? [];
  const unsavedCandidates = candidates.filter((candidate) => !savedIds.has(recommendationKey(candidate)));
  const selectedUnsavedIds = [...selectedIds].filter((id) => !savedIds.has(id));
  const suggestedRole = useMemo(() => defaultResume ? resumeSearchLabel(defaultResume) : "", [defaultResume]);
  const compatibleCriteria = useMemo(
    () => searchCriteria.filter((criterion) => !criterion.resume_profile_id || criterion.resume_profile_id === defaultResume?.id),
    [defaultResume?.id, searchCriteria],
  );
  const selectedCriterion = compatibleCriteria.find((criterion) => criterion.id === selectedCriterionId) ?? null;

  useEffect(() => {
    Promise.all([listResumeProfiles(), listJobSearchCriteria()])
      .then(([profilePayload, criteriaPayload]) => {
        const resume = profilePayload.resume_profiles.find((profile) => profile.is_default) ?? null;
        setDefaultResume(resume);
        setSearchCriteria(criteriaPayload);
        const criterion = criteriaPayload.find((item) => item.resume_profile_id === resume?.id) ?? criteriaPayload.find((item) => !item.resume_profile_id) ?? null;
        if (criterion) {
          setSelectedCriterionId(criterion.id);
          setKeyword(criterion.keyword);
          setLocation(criterion.location || "");
          setSearchEditorOpen(!criterion.location);
        } else if (resume) {
          setKeyword(resumeSearchLabel(resume));
          setSearchEditorOpen(true);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load your default resume."))
      .finally(() => setIsLoading(false));
  }, []);

  function selectCriterion(criterion: JobSearchCriterion) {
    setSelectedCriterionId(criterion.id);
    setKeyword(criterion.keyword);
    setLocation(criterion.location || "");
    setSearchEditorOpen(!criterion.location);
    setPendingCriterionSave(null);
  }

  async function refreshCriteria(preferredId?: number) {
    const criteria = await listJobSearchCriteria();
    setSearchCriteria(criteria);
    const preferred = criteria.find((criterion) => criterion.id === preferredId);
    if (preferred) selectCriterion(preferred);
    return criteria;
  }

  async function importResume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("resume") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file || isImportingResume) return;
    setError(null);
    setStatus(null);
    setResumeImport(null);
    setIsImportingResume(true);
    try {
      const result = await importResumePdf(file);
      setResumeImport(result);
      setStatus("Resume analysis is ready. Review it before using it for recommendations.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume analysis failed.");
    } finally {
      setIsImportingResume(false);
    }
  }

  async function retryResume() {
    if (!resumeImport || isImportingResume) return;
    setError(null);
    setIsImportingResume(true);
    try {
      setResumeImport(await retryResumeImport(resumeImport.document_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume analysis retry failed.");
    } finally {
      setIsImportingResume(false);
    }
  }

  async function applyResume() {
    if (!resumeImport || isApplyingResume) return;
    setError(null);
    setIsApplyingResume(true);
    try {
      const profile = await applyResumeProfileSuggestions(resumeImport);
      setDefaultResume(profile);
      setResumeImport(null);
      const criteria = await refreshCriteria();
      const generated = criteria.find((criterion) => criterion.resume_profile_id === profile.id) ?? null;
      if (generated) selectCriterion(generated);
      else {
        setKeyword(resumeSearchLabel(profile));
        setLocation("");
        setSearchEditorOpen(true);
      }
      setStatus("Your default resume is ready. Add a location to find matching jobs.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The resume profile could not be saved.");
    } finally {
      setIsApplyingResume(false);
    }
  }

  async function findJobs(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!defaultResume || !keyword.trim() || !location.trim() || isFinding) return;
    setError(null);
    setStatus(null);
    setRecommendations(null);
    setPendingCriterionSave(null);
    setSelectedIds(new Set());
    setSavedIds(new Set());
    setIsFinding(true);
    try {
      const usesSelectedCriterion = Boolean(
        selectedCriterion
        && selectedCriterion.keyword === keyword.trim()
        && (!selectedCriterion.location || selectedCriterion.location === location.trim()),
      );
      const result = await quickFindJobs(
        defaultResume.id,
        keyword.trim(),
        location.trim(),
        usesSelectedCriterion ? selectedCriterion?.id : undefined,
      );
      setRecommendations(result);
      if (usesSelectedCriterion && selectedCriterion) {
        await refreshCriteria(selectedCriterion.id);
      } else {
        setPendingCriterionSave({ keyword: result.keyword, location: result.location });
      }
      setStatus(`Found and matched ${result.candidates.length} recommended job${result.candidates.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recommended jobs could not be prepared.");
    } finally {
      setIsFinding(false);
    }
  }

  async function saveSearchCriterion() {
    if (!defaultResume || !pendingCriterionSave) return;
    setError(null);
    try {
      const saved = await createJobSearchCriterion({
        resume_profile_id: defaultResume.id,
        keyword: pendingCriterionSave.keyword,
        location: pendingCriterionSave.location,
      });
      await refreshCriteria(saved.id);
      setPendingCriterionSave(null);
      setStatus("Search criteria saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The search criteria could not be saved.");
    }
  }

  function toggleCandidate(candidate: QuickFindCandidate) {
    const id = recommendationKey(candidate);
    if (savedIds.has(id)) return;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function saveCandidates(ids: number[]) {
    if (!recommendations || !ids.length || isSaving) return;
    setError(null);
    setStatus(null);
    setIsSaving(true);
    try {
      const result = await saveQuickFindJobs(recommendations.operation_id, ids);
      const completedIds = result.imported.flatMap((item) => item.jobs_cache_id ? [item.jobs_cache_id] : []);
      setSavedIds((current) => new Set([...current, ...completedIds]));
      setSelectedIds((current) => new Set([...current].filter((id) => !completedIds.includes(id))));
      setStatus(`${result.imported.length} job${result.imported.length === 1 ? "" : "s"} saved.`);
      if (result.failed.length) setError(result.failed.map((item) => item.reason).join(" "));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The selected jobs could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return <section className="panel quick-find-page"><SkeletonRows count={4} /></section>;
  }

  return (
    <section className="panel quick-find-page">
      <PageHeader
        eyebrow="Home"
        title="Find your next opportunity"
        description="Use your default resume to find and compare five current jobs, then save only the opportunities you want."
        icon={Search}
      />
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />

      {!defaultResume ? (
        <section className="profile-card quick-find-resume-setup">
          <SectionHeader title="Start with your resume" description="Upload a PDF so DaliJob can identify suitable roles and compare each recommendation." />
          <AlertBanner tone="info">
            Personal contact information is removed before AI analysis. The generated profile is not saved until you choose Use This Resume.
          </AlertBanner>
          <form className="inline-form resume-upload-form" onSubmit={importResume}>
            <input name="resume" type="file" accept="application/pdf" required />
            <Button type="submit" icon={Upload} loading={isImportingResume}>Analyze Resume</Button>
          </form>
          {resumeImport ? (
            <section className="quick-find-resume-review">
              <div>
                <h2>{resumeImport.suggestions.headline || resumeImport.file_name}</h2>
                <p className="summary">{resumeImport.suggestions.summary || "Review the detected skills before continuing."}</p>
                <div className="resume-chip-row">
                  {resumeImport.suggestions.skills.slice(0, 8).map((skill) => <span className="resume-chip" key={skill}>{skill}</span>)}
                </div>
              </div>
              {resumeImport.parse_warning ? <AlertBanner tone="warning">{resumeImport.parse_warning}</AlertBanner> : null}
              <div className="button-row">
                {resumeImport.parse_warning ? <Button type="button" variant="secondary" loading={isImportingResume} onClick={() => void retryResume()}>Retry</Button> : null}
                <Button type="button" variant="ghost" onClick={() => setResumeImport(null)}>Discard</Button>
                <Button type="button" icon={Check} loading={isApplyingResume} disabled={Boolean(resumeImport.parse_warning)} onClick={() => void applyResume()}>Use This Resume</Button>
              </div>
            </section>
          ) : null}
          <p className="metadata">Already have a profile you want to complete manually? <a href="/profile">Open Resumes</a>.</p>
        </section>
      ) : (
        <section className="profile-card quick-find-search-card">
          <SectionHeader title="Quick job search" description={`Choose a saved search or adjust the AI-generated keywords for ${defaultResume.title}.`} />
          {!suggestedRole ? (
            <AlertBanner tone="warning">Add a target role, headline, or skills to your default resume before searching. <a href="/profile">Edit resume</a>.</AlertBanner>
          ) : null}
          {compatibleCriteria.length ? (
            <div className="quick-find-criteria-list" aria-label="Saved search criteria">
              {compatibleCriteria.map((criterion) => (
                <button
                  type="button"
                  className={`quick-find-criterion${criterion.id === selectedCriterionId ? " selected" : ""}`}
                  aria-pressed={criterion.id === selectedCriterionId}
                  onClick={() => selectCriterion(criterion)}
                  key={criterion.id}
                >
                  <span className="quick-find-criterion-copy">
                    <strong>{criterion.keyword}</strong>
                    <span>{criterion.location || "Location needed"}</span>
                  </span>
                  <span className="quick-find-criterion-source">Saved</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className="quick-find-active-search">
            <div>
              <span>Keywords</span>
              <strong>{keyword || "Add search keywords"}</strong>
            </div>
            <div>
              <span>Location</span>
              <strong>{location || "Location needed"}</strong>
            </div>
            <Button type="button" icon={Search} loading={isFinding} disabled={!keyword.trim() || !location.trim()} onClick={() => void findJobs()}>Find 5 Matches</Button>
          </div>

          <details
            className="quick-find-search-editor"
            open={searchEditorOpen}
            onToggle={(event) => setSearchEditorOpen(event.currentTarget.open)}
          >
            <summary>Change keywords or location</summary>
            <form className="quick-find-search-form" onSubmit={findJobs}>
              <label>
                Search for a job or keyword
                <input value={keyword} onChange={(event) => setKeyword(event.target.value)} maxLength={255} required />
              </label>
              <label>
                Search location
                <div className="input-with-icon"><MapPin size={17} aria-hidden="true" /><input value={location} onChange={(event) => setLocation(event.target.value)} maxLength={255} required /></div>
              </label>
              <Button type="submit" icon={Search} loading={isFinding} disabled={!keyword.trim() || !location.trim()}>Search</Button>
            </form>
          </details>
        </section>
      )}

      {recommendations ? (
        <section className="profile-card quick-find-results">
          {pendingCriterionSave ? (
            <AlertBanner tone="info">
              <div>
                <strong>Save this search?</strong>
                <p className="summary">Keep {pendingCriterionSave.keyword} in {pendingCriterionSave.location} as a reusable search option.</p>
              </div>
              <div className="button-row">
                <Button type="button" variant="ghost" onClick={() => setPendingCriterionSave(null)}>Not Now</Button>
                <Button type="button" icon={Save} onClick={() => void saveSearchCriterion()}>Save Search</Button>
              </div>
            </AlertBanner>
          ) : null}
          <div className="profile-card-header">
            <SectionHeader title="Recommended Jobs" description={`Matched with ${recommendations.resume_title} for ${recommendations.keyword} in ${recommendations.location}.`} />
            <Toolbar label="Recommendation save actions">
              <Button type="button" variant="secondary" icon={Check} disabled={!selectedUnsavedIds.length || isSaving} onClick={() => void saveCandidates(selectedUnsavedIds)}>Save Selected</Button>
              <Button type="button" icon={BriefcaseBusiness} disabled={!unsavedCandidates.length || isSaving} loading={isSaving} onClick={() => void saveCandidates(unsavedCandidates.map(recommendationKey))}>Save All</Button>
            </Toolbar>
          </div>
          {recommendations.warnings.length ? <AlertBanner tone="warning">{recommendations.warnings.map((warning) => <p key={warning}>{warning}</p>)}</AlertBanner> : null}
          {!candidates.length ? <EmptyState icon={BriefcaseBusiness} title="No recommendations found" description="Try another location or update the target roles in your default resume." /> : null}
          <div className="quick-find-result-list">
            {candidates.map((candidate) => {
              const id = recommendationKey(candidate);
              const isSaved = savedIds.has(id);
              const isSelected = selectedIds.has(id);
              return (
                <article className={`quick-find-result${isSelected ? " selected" : ""}${isSaved ? " saved" : ""}`} key={id}>
                  <label className="quick-find-result-select">
                    <input type="checkbox" checked={isSelected || isSaved} disabled={isSaved} onChange={() => toggleCandidate(candidate)} />
                    <span className="sr-only">Select {candidate.title}</span>
                  </label>
                  <MatchScoreBadge score={candidate.match_score} />
                  <div className="quick-find-result-copy">
                    <div className="job-row-title-line"><h2>{candidate.title}</h2>{isSaved ? <span className="default-label">Saved</span> : null}</div>
                    <p className="metadata">{candidate.company}{candidate.location ? ` | ${candidate.location}` : ""}</p>
                    <p className="summary">{candidate.summary || String(candidate.match_data.summary || "Match details are available after saving.")}</p>
                    <a href={candidate.source_url} target="_blank" rel="noreferrer">View source</a>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
    </section>
  );
}
