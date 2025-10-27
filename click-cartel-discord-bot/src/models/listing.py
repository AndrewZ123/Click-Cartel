class Listing:
    def __init__(self, id: int, site: str, title: str, payout: float, link: str, date_posted: str, approved: bool = False):
        self.id = id
        self.site = site
        self.title = title
        self.payout = payout
        self.link = link
        self.date_posted = date_posted
        self.approved = approved

    def approve(self):
        self.approved = True

    def __repr__(self):
        return f"<Listing id={self.id} title='{self.title}' site='{self.site}' payout={self.payout}>"