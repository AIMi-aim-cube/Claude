# Deployment

## Vercel

1. Push this folder to GitHub.
2. Import repo in Vercel.
3. Add environment variables from `.env.example`.
4. Deploy.
5. Add domain: `chataimi.ai` or `app.chataimi.ai`.

## DNS

In your domain registrar, point the domain to Vercel using the records Vercel gives you.

## Data safety

Never expose broker API keys, Google credentials, or Firebase admin credentials in frontend variables. Keep server secrets without `NEXT_PUBLIC_`.
