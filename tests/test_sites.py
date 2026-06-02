"""Tests for lgwks_sites — site-aware extraction for Twitter/X, Reddit, Google Scholar."""

from __future__ import annotations

import unittest

import lgwks_sites as sites


class TestTwitter(unittest.TestCase):
    def test_extracts_meta_tags(self):
        html = '''
        <html><head>
        <meta name="twitter:title" content="Breaking: something happened" />
        <meta name="twitter:description" content="Details here." />
        <meta name="twitter:creator" content="@newsdesk" />
        </head><body>100 likes</body></html>
        '''
        r = sites.extract_twitter("https://twitter.com/newsdesk/status/123", html)
        self.assertEqual(r["kind"], "twitter")
        self.assertEqual(r["title"], "Breaking: something happened")
        self.assertEqual(r["body"], "Details here.")
        self.assertEqual(r["author"], "@newsdesk")
        self.assertTrue(r["ok"])
        self.assertFalse(r["fallback"])

    def test_extracts_tweet_text_div(self):
        html = '''
        <div data-testid="tweetText">This is the actual tweet content with hashtags #ai</div>
        <meta name="twitter:description" content="Fallback desc" />
        '''
        r = sites.extract_twitter("https://x.com/user/status/456", html)
        self.assertEqual(r["body"], "This is the actual tweet content with hashtags #ai")
        self.assertTrue(r["ok"])

    def test_empty_body_is_fallback(self):
        r = sites.extract_twitter("https://twitter.com/user/status/456", "<html></body></html>")
        self.assertFalse(r["ok"])
        self.assertTrue(r["fallback"])


class TestReddit(unittest.TestCase):
    def test_new_reddit_shreddit(self):
        html = '''
        <html><title>The post title | r/subreddit</title>
        <shreddit-post title="The post title"></shreddit-post>
        <div class="text-neutral-content">This is the post body.</div>
        <faceplate-number number="142"></faceplate-number>
        <shreddit-comment><p>First comment</p></shreddit-comment>
        </html>
        '''
        r = sites.extract_reddit("https://reddit.com/r/subreddit/comments/abc/title", html)
        self.assertEqual(r["kind"], "reddit")
        self.assertEqual(r["title"], "The post title")
        self.assertEqual(r["body"], "This is the post body.")
        self.assertEqual(r["metrics"]["upvotes"], 142)
        self.assertIn("First comment", r["extra"]["comments"])
        self.assertTrue(r["ok"])

    def test_old_reddit_fallback(self):
        html = '''
        <html><title>Old title</title>
        <a class="title">Old post title</a>
        <div class="usertext-body">Old body text</div>
        </html>
        '''
        r = sites.extract_reddit("https://old.reddit.com/r/sub/comments/abc", html)
        self.assertEqual(r["title"], "Old post title")
        self.assertEqual(r["body"], "Old body text")
        self.assertTrue(r["ok"])


class TestScholar(unittest.TestCase):
    def test_result_page_extraction(self):
        html = '''
        <div class="gs_rt"><a href="https://example.com/paper">Attention Is All You Need</a></div>
        <div class="gs_a">A Vaswani, N Shazeer, N Parmar - Advances in neural ... 2017</div>
        <div class="gs_rs">We propose a new simple network architecture...</div>
        Cited by 84422
        <a href="https://example.com/paper.pdf">[PDF]</a>
        '''
        r = sites.extract_scholar("https://scholar.google.com/scholar?q=attention", html)
        self.assertEqual(r["kind"], "scholar")
        self.assertEqual(r["title"], "Attention Is All You Need")
        self.assertIn("Vaswani", r["author"])
        self.assertEqual(r["metrics"]["citations"], 84422)
        self.assertEqual(r["extra"]["pdf_url"], "https://example.com/paper.pdf")
        self.assertTrue(r["ok"])

    def test_bib_page_extraction(self):
        html = '''
        <div class="gsc_oci_title">BERT: Pre-training</div>
        <div class="gs_oci_field">Authors</div><div class="gs_oci_value">J Devlin</div>
        <div class="gs_oci_field">Year</div><div class="gs_oci_value">2019</div>
        '''
        r = sites.extract_scholar("https://scholar.google.com/citations?user=abc", html)
        self.assertEqual(r["title"], "BERT: Pre-training")
        self.assertEqual(r["author"], "J Devlin")
        self.assertEqual(r["date"], "2019")
        self.assertTrue(r["ok"])

    def test_no_match_is_fallback(self):
        r = sites.extract_scholar("https://scholar.google.com/scholar?q=xyz", "<html></body></html>")
        self.assertFalse(r["ok"])
        self.assertTrue(r["fallback"])


class TestDispatch(unittest.TestCase):
    def test_twitter_host(self):
        self.assertIsNotNone(sites.extract_for_site("https://twitter.com/user/status/1", "<html></html>"))
        self.assertIsNotNone(sites.extract_for_site("https://x.com/user/status/1", "<html></html>"))

    def test_unknown_host_returns_none(self):
        self.assertIsNone(sites.extract_for_site("https://example.com/article", "<html></html>"))

    def test_supported_host(self):
        self.assertTrue(sites.supported_host("https://reddit.com/r/test"))
        self.assertFalse(sites.supported_host("https://example.com"))


if __name__ == "__main__":
    unittest.main()
