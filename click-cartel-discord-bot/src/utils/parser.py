def parse_listing(html_content):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, 'html.parser')
    listings = []

    for listing in soup.find_all('div', class_='listing'):
        title = listing.find('h2', class_='title').get_text(strip=True)
        payout = listing.find('span', class_='payout').get_text(strip=True)
        link = listing.find('a', class_='link')['href']
        date_posted = listing.find('span', class_='date-posted').get_text(strip=True)

        listings.append({
            'title': title,
            'payout': payout,
            'link': link,
            'date_posted': date_posted
        })

    return listings

def parse_review(html_content):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, 'html.parser')
    reviews = []

    for review in soup.find_all('div', class_='review'):
        reviewer = review.find('span', class_='reviewer').get_text(strip=True)
        content = review.find('p', class_='content').get_text(strip=True)
        date = review.find('span', class_='date').get_text(strip=True)

        reviews.append({
            'reviewer': reviewer,
            'content': content,
            'date': date
        })

    return reviews