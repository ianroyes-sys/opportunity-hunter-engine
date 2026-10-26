import unittest

import ats_feed as feed


class AtsFeedFilters(unittest.TestCase):
    def test_locations_keep_major_us_and_us_remote_only(self):
        ok = ["Cambridge, MA", "NYC", "Remote in USA", "Remote, United States", "San Francisco, CA, United States"]
        bad = ["Cambridge, Cambridgeshire, England, United Kingdom", "London, UK", "Remote in Canada",
               "Detroit, MI", "Rolla, MO", "Bangalore, India"]
        for loc in ok:
            self.assertTrue(feed.us_location([loc], excluded=["detroit"]), loc)
        for loc in bad:
            self.assertFalse(feed.us_location([loc], excluded=["detroit"]), loc)

    def test_titles_are_entry_level_and_in_function(self):
        for title in ["Operations Associate", "Product Intern", "Business Development Representative",
                      "Founder's Associate", "Summer 2027 Finance Intern"]:
            self.assertTrue(feed.fits_title(title), title)
        for title in ["Senior Product Manager", "Account Executive", "AI Trainer - Bosnian",
                      "Director of Operations", "Mechanical Engineering Intern", "Software Engineer II"]:
            self.assertFalse(feed.fits_title(title), title)

    def test_simplify_categories(self):
        self.assertTrue(feed.fits_title("Product Management Intern", "Product"))
        self.assertTrue(feed.fits_title("iOS Engineer Intern", "Software"))
        self.assertFalse(feed.fits_title("Backend Infrastructure Intern", "Software"))
        self.assertFalse(feed.fits_title("Hardware Intern", "Hardware"))

    def test_clean_url_drops_tracking(self):
        self.assertEqual(feed.clean_url("https://job-boards.greenhouse.io/scaleai/jobs/1?utm_source=Simplify&ref=Simplify"),
                         "https://job-boards.greenhouse.io/scaleai/jobs/1")
        self.assertEqual(feed.ats_of("https://jobs.ashbyhq.com/ramp/abc"), ("ashby", "ramp"))


if __name__ == "__main__":
    unittest.main()
