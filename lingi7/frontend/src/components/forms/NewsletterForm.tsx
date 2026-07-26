import React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import toast from "react-hot-toast";
import { z } from "zod";

const schema = z.object({ email: z.string().email("Enter a valid email address.") });
type NewsletterValues = z.infer<typeof schema>;

export const NewsletterForm: React.FC = () => {
  const { register, handleSubmit, formState: { errors, isSubmitting }, reset } = useForm<NewsletterValues>({ resolver: zodResolver(schema) });
  const submit = async (values: NewsletterValues) => { await new Promise((resolve) => window.setTimeout(resolve, 250)); toast.success(`Welcome to Lingi7, ${values.email}`); reset(); };
  return <form className="w-full max-w-md" onSubmit={handleSubmit(submit)} noValidate><div className="flex gap-2"><input {...register("email")} className="min-w-0 flex-1 rounded-xl border border-slate-200 px-4 text-sm outline-none focus:border-blue-500" type="email" placeholder="Your email address" aria-label="Email address" /><button disabled={isSubmitting} className="rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white disabled:opacity-60">{isSubmitting ? "Joining…" : "Join us"}</button></div>{errors.email && <p className="mt-2 text-xs font-medium text-red-600">{errors.email.message}</p>}</form>;
};
