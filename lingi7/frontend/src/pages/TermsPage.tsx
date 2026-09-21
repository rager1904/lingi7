/** TermsPage — terms of service for Lingi7 */

import React from "react";

const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <section className="space-y-3">
    <h2 className="text-lg font-bold text-slate-900">{title}</h2>
    <div className="space-y-3 text-sm leading-7 text-gray-600">{children}</div>
  </section>
);

const TermsPage: React.FC = () => (
  <div className="mx-auto max-w-3xl px-4 py-12 space-y-10 sm:px-6">
    <div className="space-y-3">
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">LEGAL</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">
        Terms of Service
      </h1>
      <p className="text-sm text-gray-500">Last updated: September 2026</p>
    </div>

    <Section title="1. Acceptance of terms">
      <p>
        By creating an account or using Lingi7, you agree to these terms. If
        you do not agree, please do not use the platform.
      </p>
    </Section>

    <Section title="2. Accounts and eligibility">
      <p>
        You must be at least 18 years old to use the platform. You agree to
        provide accurate information and keep your password secure. KYC
        identity verification may be required before you can transact.
      </p>
    </Section>

    <Section title="3. Buying and selling">
      <p>
        Sellers are responsible for the accuracy of their listings, prices
        (in Kwacha), and fulfilment. Buyers agree to pay for confirmed orders.
        Payments are processed through escrow: funds are held until both
        parties confirm satisfaction.
      </p>
    </Section>

    <Section title="4. Prohibited conduct">
      <ul className="list-disc space-y-2 pl-5">
        <li>Fraudulent listings, misrepresentation, or counterfeit goods.</li>
        <li>Money laundering or any illegal activity.</li>
        <li>Harassment, abuse, or impersonation of others.</li>
        <li>Attempting to bypass escrow or platform fees.</li>
      </ul>
    </Section>

    <Section title="5. Disputes">
      <p>
        If a transaction goes wrong, open a dispute from your orders page.
        Lingi7 will mediate fairly between buyer and seller using evidence
        such as photos and tracking records.
      </p>
    </Section>

    <Section title="6. Limitation of liability">
      <p>
        Lingi7 acts as a marketplace facilitator and is not a party to the
        underlying sale. We are not liable for indirect losses. Nothing in
        these terms limits your statutory rights under Zambian law.
      </p>
    </Section>

    <Section title="7. Changes to these terms">
      <p>
        We may update these terms from time to time. Continued use of the
        platform after changes are published means you accept the updated
        terms.
      </p>
    </Section>
  </div>
);

export default TermsPage;