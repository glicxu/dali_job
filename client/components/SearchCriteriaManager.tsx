"use client";

import { FormEvent, useEffect, useState } from "react";
import { Pencil, Save, Search, Trash2, X } from "lucide-react";
import {
  deleteJobSearchCriterion,
  JobSearchCriterion,
  listJobSearchCriteria,
  updateJobSearchCriterion,
} from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, IconButton, SectionHeader, SkeletonRows, ToastRegion } from "./ui";

export function SearchCriteriaManager() {
  const [criteria, setCriteria] = useState<JobSearchCriterion[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [keyword, setKeyword] = useState("");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    listJobSearchCriteria()
      .then(setCriteria)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load saved searches."))
      .finally(() => setLoading(false));
  }, []);

  function beginEdit(criterion: JobSearchCriterion) {
    setEditingId(criterion.id);
    setKeyword(criterion.keyword);
    setLocation(criterion.location || "");
    setError(null);
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingId || !keyword.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateJobSearchCriterion(editingId, {
        keyword: keyword.trim(),
        location: location.trim(),
      });
      setCriteria((current) => current.map((criterion) => criterion.id === updated.id ? updated : criterion));
      setEditingId(null);
      setStatus("Saved search updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The saved search could not be updated.");
    } finally {
      setSaving(false);
    }
  }

  async function removeCriterion(criterion: JobSearchCriterion) {
    if (!window.confirm(`Delete the saved search for "${criterion.keyword}"?`)) return;
    setError(null);
    try {
      await deleteJobSearchCriterion(criterion.id);
      setCriteria((current) => current.filter((item) => item.id !== criterion.id));
      if (editingId === criterion.id) setEditingId(null);
      setStatus("Saved search deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The saved search could not be deleted.");
    }
  }

  return (
    <section className="profile-card account-search-criteria">
      <SectionHeader title="Saved searches" description="Edit or remove the keyword and location combinations available from the Home page." />
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />
      {loading ? <SkeletonRows count={2} /> : null}
      {!loading && !criteria.length ? <EmptyState compact icon={Search} title="No saved searches" description="Run a Quick Find search from Home and save it for reuse." /> : null}
      <div className="account-search-criteria-list">
        {criteria.map((criterion) => editingId === criterion.id ? (
          <form className="account-search-criterion-edit" onSubmit={saveEdit} key={criterion.id}>
            <label>
              Search for a job or keyword
              <input value={keyword} onChange={(event) => setKeyword(event.target.value)} maxLength={255} required />
            </label>
            <label>
              Location
              <input value={location} onChange={(event) => setLocation(event.target.value)} maxLength={255} />
            </label>
            <div className="button-row">
              <Button type="submit" size="compact" icon={Save} loading={saving}>Save</Button>
              <Button type="button" size="compact" variant="ghost" icon={X} onClick={() => setEditingId(null)}>Cancel</Button>
            </div>
          </form>
        ) : (
          <article className="account-search-criterion" key={criterion.id}>
            <div>
              <strong>{criterion.keyword}</strong>
              <p className="metadata">{criterion.location || "Location needed"}</p>
            </div>
            <Badge tone={criterion.source === "resume_generated" ? "info" : "neutral"}>
              {criterion.source === "resume_generated" ? "From resume" : "Saved"}
            </Badge>
            <div className="button-row">
              <IconButton label={`Edit ${criterion.keyword}`} icon={Pencil} variant="ghost" onClick={() => beginEdit(criterion)} />
              <IconButton label={`Delete ${criterion.keyword}`} icon={Trash2} variant="danger" onClick={() => void removeCriterion(criterion)} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
