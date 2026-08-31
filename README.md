# LearnWithZuhaib — Tech Blog + Free Udemy Courses

Two main sections:

1. **Tech Blog** (`/blog/`) — AI/ML articles (auto-generated daily)
2. **Free Udemy Courses** (`/courses/`) — 100% OFF coupon list (similar to [e-next Udemy list](https://jobs.e-next.in/course/udemy/1))

## Enable GitHub Pages

1. Repo **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / folder: `/ (root)`
4. Site URL: `https://zuhaibbutt786.github.io/tech-blog-courses/`

## Secrets

Add repository secret:

- `GROQ_API_KEY` — for daily blog generation

## Automation

Workflow **Update courses and blog** runs daily at 11:00 AM PKT:

- Fetches free course lists → `data/courses.json`
- Writes 2 blog posts → `blog/*.html` + `data/posts.json`

Manual run: **Actions → Update courses and blog → Run workflow**

## Local

```bash
pip install requests beautifulsoup4
export GROQ_API_KEY=...
python scripts/fetch_courses.py
python scripts/generate_posts.py
```

## Monetization later

After traffic grows: Google AdSense, affiliates, newsletter. Prefer quality over 15 thin posts/day.

## Disclaimer

Not affiliated with Udemy. Coupons are instructor promotional codes and may expire.
