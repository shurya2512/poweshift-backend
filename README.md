This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Poweshift backend

The setup pages expose all 22 promoted ego profiles and only the tracks available for each session.
The review fixture itself renders a 23-car field; diagnostic reports retain 22 source cars plus the
independently controlled P23 ego.
They carry the selected mode, track and profile into a source-bound diagnostic report. The race
report separates the added P23 ego from the fixed 22-car reference field and shows every reported
lap, opportunity, action and race-control alignment. Configure another local backend or run ID:

```bash
NEXT_PUBLIC_POWESHIFT_API_URL=http://localhost:8000
NEXT_PUBLIC_POWESHIFT_RUN_ID=selection-run
```

The animated race world remains clearly labelled as a review fixture until the backend supplies an
admitted full-world stream. Report times are source timestamps and may start after 0:00 when the
first complete 22-car source tick occurs.
The policy transport also exports `openLivePolicy` for strict 4 Hz observation input and 5 Hz
recommendations without presenting diagnostic output as physically admitted.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
