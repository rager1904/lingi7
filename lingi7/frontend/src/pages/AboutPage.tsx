/** AboutPage — company story, mission, and platform highlights */

import React from "react";
import { Link } from "react-router-dom";

const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <section className="space-y-3">
    <h2 className="text-xl font-bold text-slate-900">{title}</h2>
    <div className="space-y-3 text-sm leading-7 text-gray-600">{children}</div>
  </section>
);

const AboutPage: React.FC = () => (
  <div className="mx-auto max-w-3xl px-4 py-12 space-y-10 sm:px-6">
    <div className="space-y-3">
      <p className="text-sm font-bold tracking-[.16em] text-blue-600">ABOUT US</p>
      <h1 className="text-4xl font-black tracking-tight text-slate-950">
        About Lingi7
      </h1>
      <p className="text-base leading-7 text-gray-600">
        Lingi7 is a Zambian marketplace built for better commerce — helping
        people discover, buy, and sell with confidence across Zambia.
      </p>
    </div>

    <Section title="Our mission">
      <p>
        We exist to make buying and selling online safe, simple, and fair for
        every Zambian. From Lusaka to Livingstone, we connect trusted sellers
        with buyers and protect every transaction with escrow, verified
        identity (KYC), and transparent logistics.
      </p>
    </Section>

    <Section title="Built for Zambia">
      <p>
        All prices are in Zambian Kwacha (ZMW). Payments support mobile money
        via MTN MoMo and Airtel Money. Identity is verified using the National
        Registration Card (NRC), in line with Bank of Zambia requirements and
        the Data Protection Act 2021.
      </p>
    </Section>

    <Section title="How we keep transactions safe">
      <ul className="list-disc space-y-2 pl-5">
        <li>
          <strong>Escrow payments</strong> — money is held securely until you
          confirm delivery.
        </li>
        <li>
          <strong>Identity verification</strong> — buyers and sellers complete
          KYC before high-value transactions.
        </li>
        <li>
          <strong>Order tracking</strong> — follow your package from the
          seller to your door.
        </li>
        <li>
          <strong>Dispute resolution</strong> — our team steps in when things
          go wrong.
        </li>
      </ul>
    </Section>

    <section className="space-y-3">
      <h2 className="text-xl font-bold text-slate-900">Get started</h2>
      <div className="flex flex-wrap gap-3">
        <Link to="/register" className="btn-primary">
          Create an account
        </Link>
        <Link to="/shop" className="btn-primary">
          Browse products
        </Link>
      </div>
    </section>
  </div>
);

export default AboutPage;