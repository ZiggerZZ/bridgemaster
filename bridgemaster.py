import requests
from bs4 import BeautifulSoup
import random
import pickle
import dataset

db = dataset.connect()  # reads env url DATABASE_URL
table = db['bridgemaster']

cache = {}


def hand_str_to_dict(s):
    """s='S2H6789D89TJQC678'"""
    others, clubs = s.split('C')
    others, diamonds = others.split('D')
    others, hearts = others.split('H')
    others, spades = others.split('S')
    return {
        'C': list(clubs),
        'D': list(diamonds),
        'H': list(hearts),
        'S': list(spades)
    }


def hand_dict_to_list(d):
    return ['C' + x for x in d['C']] + ['D' + x for x in d['D']] + ['H' + x for x in d['H']] + ['S' + x for x in d['S']]


def next_player(player):
    match player:
        case 'W':
            return 'N'
        case 'N':
            return 'E'
        case 'E':
            return 'S'
        case 'S':
            return 'W'


def rank(card):
    """card='H8'"""
    rank = card[1]
    match card[1]:
        case '2':
            return 1
        case '3':
            return 2
        case '4':
            return 3
        case '5':
            return 4
        case '6':
            return 5
        case '7':
            return 6
        case '8':
            return 7
        case '9':
            return 8
        case 'T':
            return 9
        case 'J':
            return 10
        case 'Q':
            return 11
        case 'K':
            return 12
        case 'A':
            return 13


class Deal:
    headers = {
        'Connection': 'keep-alive',
        'sec-ch-ua': '"Chromium";v="92", " Not A;Brand";v="99", "Sidekick";v="92"',
        'Accept': 'application/json, text/plain, */*',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://www.bridgebase.com',
        'Sec-Fetch-Site': 'same-site',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://www.bridgebase.com/',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
    }
    const_data = {
        'v3b': 'web',
        'v3v': '6.0.2',
        'v3u': 'BBO1',
        'cbust': '0.52197'
    }

    def __init__(self, handid):
        self.handid = handid
        self.request_id = 1
        # init cache
        # if handid not in cache:
        #     cache[handid] = {}
        data = {'handid': handid, 'history': '', 'request_id': str(self.request_id), **Deal.const_data}
        response = requests.post('https://webutil.bridgebase.com/v2/bmweb/bm.php', headers=Deal.headers, data=data)
        parsed_xml = BeautifulSoup(response.text, features="html.parser")
        self.bidding = parsed_xml.sc_bmapi.sc_bridgemaster['bidding']
        self.north = hand_str_to_dict(parsed_xml.sc_bmapi.sc_bridgemaster['north'])
        self.south = hand_str_to_dict(parsed_xml.sc_bmapi.sc_bridgemaster['south'])
        self.card = parsed_xml.sc_bmapi.sc_bridgemaster['card']
        self.history = parsed_xml.sc_bmapi['history'] + self.card
        self.denomination = self.bidding.strip('-').strip('P').strip('R').strip('P').strip('D').strip('P')[-1]
        self.level = int(self.bidding.strip('-').strip('P').strip('R').strip('P').strip('D').strip('P')[-2])
        self.trick = [('W', self.card)]
        self.player = 'N'  # who's turn to play
        self.ew_tricks = 0

    def __str__(self):
        return f'{self.north}\n\n\t{self.card}\n\n{self.south}'

    def __repr__(self):
        return f'{self.north}\n\n\t{self.card}\n\n{self.south}'

    def play(self, card=None):
        """If card is None, pick a random card"""
        if self.player in {"E", "W"}:
            self.request_id += 1
            data = {'handid': self.handid, 'request_id': str(self.request_id), 'history': self.history,
                    **Deal.const_data}
            response = requests.post('https://webutil.bridgebase.com/v2/bmweb/bm.php', headers=Deal.headers, data=data)
            parsed_xml = BeautifulSoup(response.text, features="html.parser")
            card = parsed_xml.sc_bmapi.sc_bridgemaster['card']
            # remove '**' in case when an opponent had won a trick
            self.history = self.history.replace('*', '')
        else:
            if not card:
                cards = self.north if self.player == 'N' else self.south
                if self.trick:
                    first_card = self.trick[0][1]
                    suit = first_card[0]
                    if suit_cards := cards[suit]:
                        random_card_rank = random.choice(suit_cards)
                        card = suit + random_card_rank
                        suit_cards.remove(random_card_rank)
                    else:
                        card = random.choice(hand_dict_to_list(cards))
                        card_suit = card[0]
                        cards[card_suit].remove(card[1])
                else:
                    card = random.choice(hand_dict_to_list(cards))
                    card_suit = card[0]
                    cards[card_suit].remove(card[1])
            else:
                card_suit = card[0]
                cards[card_suit].remove(card[1])

        print(card)
        new_history = self.history + card  # parsed_xml.sc_bmapi['history']
        self.trick.append((self.player, card))
        self.card = card
        self.history = new_history

        if len(self.trick) < 4:
            self.player = next_player(self.player)
        else:
            print()
            leader, lead = self.trick[0]
            suited_plays = [(player, card[1]) for (player, card) in self.trick if card[0] == lead[0]]
            trump_plays = [(player, card[1]) for (player, card) in self.trick if card[0] == self.denomination]
            sorted_plays = sorted(suited_plays, key=lambda card: rank(card)) + sorted(trump_plays,
                                                                                      key=lambda card: rank(card))
            # The winning play is the last element in sorted_plays
            trick_winner = sorted_plays[-1][0]
            self.player = trick_winner
            if trick_winner in {'E', 'W'}:
                self.history += "**"
                self.ew_tricks += 1
            self.trick = []

        # cache[self.handid][new_history] = self.card
        table.insert(dict(hand=self.handid, history=new_history, card=self.card))


def read_problems_list(name):
    with open(name, "r") as file:
        content = file.readlines()
        # Combine the lines in the list into a string
        content = "".join(content)
        bs_content = BeautifulSoup(content, "html.parser")
        hand_names = [d['handid'] for d in bs_content.find_all('bmhand')]
        return hand_names


def sample_game(deal):
    print(deal)
    for n in range(1):
        print('Game number', n + 1)
        d = Deal(handid=deal)
        print(d.card)
        # print(Duck3.history, Duck3.trick, Duck3.player)
        for _ in range(51):
            d.play()
            if d.ew_tricks + (d.level + 6) > 13:
                print("Game", n + 1, "finished. NS lost.")
                break
            # print(Duck3.history, Duck3.trick, Duck3.player)


if __name__ == '__main__':
    sample_game('2/Trump39.c18')  # doubled contract
    sample_game('3/Duck3.a1')
    # for level in range(1, 6):
    #     problem_names = read_problems_list(f'level{level}.xml')
    #     # deal = '3/Suit16.a2'
    #     for deal in problem_names:
    #         sample_game(deal)

    # with open('five_levels.pkl', 'wb') as f:
    #     pickle.dump(cache, f)

# with open('saved_dictionary.pkl', 'rb') as f:
#         loaded_dict = pickle.load(f)
