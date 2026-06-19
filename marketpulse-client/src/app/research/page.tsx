import { redirect } from 'next/navigation';

/**
 * BTC Research Lab entry point (W5 T22).
 *
 * The lab is now multi-asset and lives at ``/research/{asset}``. This bare
 * ``/research`` URL preserves back-compat by redirecting to the BTC default —
 * the original primary asset — so existing bookmarks and links keep working.
 *
 * The redirect is a server component so it happens before any client JS is
 * shipped for this route (no flash of content).
 */
export default function ResearchPage() {
  redirect('/research/BTC');
}
