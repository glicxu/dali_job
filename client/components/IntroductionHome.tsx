"use client";

import { useEffect, useState } from "react";
import { ArrowRight, BriefcaseBusiness, FileText, GraduationCap, Target } from "lucide-react";
import { getAuthToken } from "../lib/api";

export function IntroductionHome() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    setIsAuthenticated(Boolean(getAuthToken()));
  }, []);

  return (
    <section className="panel introduction-home">
      <section className="introduction-primary">
        <div className="introduction-copy">
          <p className="eyebrow">Resume-guided job search</p>
          <h1>Find the jobs that match your resume best.</h1>
          <p className="lede">
            DaliJob helps you organize resumes and job opportunities, compare your experience with job requirements,
            and focus your search on roles where your background is the strongest fit.
          </p>
          <a className="button-link introduction-start-action action-with-icon" href={isAuthenticated ? "/tutorial?replay=1" : "/auth"}>
            <GraduationCap size={18} aria-hidden="true" /> Getting Started
          </a>
        </div>

        <div className="introduction-match-visual" aria-label="Example resume and job match">
          <div className="introduction-source">
            <span className="introduction-icon"><FileText size={21} aria-hidden="true" /></span>
            <div>
              <span>Your resume</span>
              <strong>Skills and experience</strong>
            </div>
          </div>
          <ArrowRight className="introduction-arrow" size={24} aria-hidden="true" />
          <div className="introduction-source">
            <span className="introduction-icon"><BriefcaseBusiness size={21} aria-hidden="true" /></span>
            <div>
              <span>Job opportunity</span>
              <strong>Requirements and keywords</strong>
            </div>
          </div>
          <div className="introduction-score">
            <Target size={22} aria-hidden="true" />
            <div><strong>8/10</strong><span>Example match</span></div>
          </div>
        </div>
      </section>

      <section className="introduction-summary" aria-label="DaliJob workflow summary">
        <div><strong>Build your resume profile</strong><span>Keep reusable career information in one place.</span></div>
        <div><strong>Review better-fit jobs</strong><span>See matched skills, missing requirements, and a clear score.</span></div>
        <div><strong>Manage your progress</strong><span>Save opportunities and track applications through each stage.</span></div>
      </section>
    </section>
  );
}
