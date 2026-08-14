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
          <p className="eyebrow">Find your best fit</p>
          <h1>Find the job that suits you most</h1>
          <p className="lede">
            Compare your resume with job requirements, save strong matches, and manage your applications in one place.
          </p>
          <a className="button-link introduction-start-action action-with-icon" href={isAuthenticated ? "/tutorial?replay=1" : "/auth"}>
            <GraduationCap size={18} aria-hidden="true" /> Getting Started
          </a>
        </div>

        <div className="introduction-match-visual" aria-label="Example resume and job match">
          <div className="introduction-source">
            <span className="introduction-icon"><FileText size={21} aria-hidden="true" /></span>
            <div>
              <span>Resume</span>
              <strong>Your experience</strong>
            </div>
          </div>
          <ArrowRight className="introduction-arrow" size={24} aria-hidden="true" />
          <div className="introduction-source">
            <span className="introduction-icon"><BriefcaseBusiness size={21} aria-hidden="true" /></span>
            <div>
              <span>Job</span>
              <strong>What they need</strong>
            </div>
          </div>
          <div className="introduction-score">
            <Target size={22} aria-hidden="true" />
            <div><strong>8/10</strong><span>Example match</span></div>
          </div>
        </div>
      </section>

      <section className="introduction-summary" aria-label="DaliJob workflow summary">
        <div><strong>Add your resume</strong><span>Build a reusable profile.</span></div>
        <div><strong>Compare jobs</strong><span>See strengths, gaps, and a match score.</span></div>
        <div><strong>Track applications</strong><span>Keep every opportunity organized.</span></div>
      </section>
    </section>
  );
}
