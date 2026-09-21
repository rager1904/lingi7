/** PrivacyPage — data protection & privacy policy for Lingi7 */

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

const PrivacyPage: React.FC = () => (
  <div className="mx-auto max-w-3xl px-4 py-12 space-y-10 sm:px-6">
    <div className="space-y-3">
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">PRIVACY</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">
        Privacy Policy
      </h1>
      <p className="text-sm text-gray-500">Last updated: September 2026</p>
    </div>

    <Section title="What we collect">
      <p>
        We collect the information you give us when you create an account:
        your name, phone number, email address, delivery address, and — during
        KYC verification — your NRC number and identity documents. We also
        collect order and transaction records so we can operate the platform.
      </p>
    </Section>

    <Section title="How we use your data">
      <ul className="list-disc space-y-2 pl-5">
        <li>Verify your identity and fight fraud (KYC).</li>
        <li>Process orders, payments, and refunds.</li>
        <li>Provide customer support and dispute resolution.</li>
        <li>Send important service notifications such as order updates.</li>
      </ul>
    </Section>

    <Section title="How we protect it">
      <p>
        Your documents and personal data are encrypted in transit and at rest.
        Access is restricted to authorised staff, and administrator actions are
        logged on an immutable audit trail. We follow the Zambian Data
        Protection Act 2021.
      </p>
    </Section>

    <Section title="Who we share it with">
      <p>
        We never sell your data. We share information only with parties needed
        to fulfil your order — such as payment processors (MTN MoMo, Airtel
        Money) and logistics partners — and with regulators when the law
        requires it.
      </p>
    </Section>

    <Section title="Your rights">
      <p>
        You may request a copy of the personal data we hold about you, ask us
        to correct it, or request its deletion. Contact support from your
        account page to exercise these rights.
      </p>
    </Section>

    <Section title="Retention">
      <p>
        We keep KYC records and transaction histories for as long as required
        by Zambian financial-services regulations, after which they are
        securely deleted.
      </p>
    </Section>
  </div>
);

export default PrivacyPage;