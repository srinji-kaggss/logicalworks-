//! robots.txt compliance. Default policy respects robots strictly; the engine
//! only ignores it when CrawlConfig.respect_robots is explicitly false (the
//! Aggressive ladder rung, for authorized targets). Crawl-delay and sitemap
//! hints are extracted for the politeness layer and the frontier seeder.

use texting_robots::Robot;

pub struct RobotsRules {
    robot: Robot,
    /// crawl-delay in milliseconds if the site declared one.
    pub crawl_delay_ms: Option<u64>,
    pub sitemaps: Vec<String>,
}

impl RobotsRules {
    /// Parse robots.txt for our user-agent. On parse failure we fail OPEN with a
    /// permissive ruleset but surface it — //why: a malformed robots.txt should
    /// not silently block a whole crawl, but the caller logs the parse error.
    pub fn parse(user_agent: &str, body: &[u8]) -> Result<Self, String> {
        match Robot::new(user_agent, body) {
            Ok(robot) => {
                let crawl_delay_ms = robot.delay.map(|secs| (secs as f64 * 1000.0) as u64);
                let sitemaps = robot.sitemaps.iter().map(|u| u.to_string()).collect();
                Ok(Self { robot, crawl_delay_ms, sitemaps })
            }
            Err(e) => Err(e.to_string()),
        }
    }

    /// Permissive ruleset used when no robots.txt is reachable (404 / network).
    pub fn allow_all() -> Self {
        // An empty robots.txt allows everything per the standard.
        let robot = Robot::new("*", b"").expect("empty robots parses");
        Self { robot, crawl_delay_ms: None, sitemaps: Vec::new() }
    }

    pub fn allowed(&self, url: &str) -> bool {
        self.robot.allowed(url)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disallow_is_respected() {
        let txt = b"User-agent: *\nDisallow: /private\n";
        let rules = RobotsRules::parse("lgwks-crawler", txt).unwrap();
        assert!(rules.allowed("https://x.com/public/page"));
        assert!(!rules.allowed("https://x.com/private/secret"));
    }

    #[test]
    fn crawl_delay_parsed_to_ms() {
        let txt = b"User-agent: *\nCrawl-delay: 2\nDisallow:\n";
        let rules = RobotsRules::parse("lgwks-crawler", txt).unwrap();
        assert_eq!(rules.crawl_delay_ms, Some(2000));
    }

    #[test]
    fn allow_all_permits_everything() {
        let rules = RobotsRules::allow_all();
        assert!(rules.allowed("https://anything.com/any/path"));
    }
}
