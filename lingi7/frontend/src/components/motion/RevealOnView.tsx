import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useInView } from "react-intersection-observer";

const RevealOnView: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ children, className }) => {
  const reducedMotion = useReducedMotion();
  const { ref, inView } = useInView({ triggerOnce: true, rootMargin: "0px 0px -8%" });
  return <motion.div ref={ref} className={className} initial={reducedMotion ? false : { opacity: 0, y: 18 }} animate={reducedMotion || inView ? { opacity: 1, y: 0 } : undefined} transition={{ duration: 0.42, ease: "easeOut" }}>{children}</motion.div>;
};
export default RevealOnView;
