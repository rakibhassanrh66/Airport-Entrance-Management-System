#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char name[100];
    char destination[100];
    int hours;
    int minutes;
    char am_pm[3];
} Ticket;

typedef struct node {
    Ticket ticket;
    struct node* next;
} Node;

Node* head = NULL;

int validateID(int id) {
    if (id >= 1 && id <= 1000)
        return 1;
    else {
        printf("Wrong ID. Please enter a valid ID (1-1000).\n");
        return 0;
    }
}

int validateTime(int hours, int minutes, const char* am_pm) {
    if (hours >= 1 && hours <= 12 && minutes >= 0 && minutes <= 59 && (strcmp(am_pm, "AM") == 0 || strcmp(am_pm, "PM") == 0))
        return 1;
    else {
        printf("Invalid time format. Please enter a valid time (hh:mm AM/PM).\n");
        return 0;
    }
}

void checkVerificationID() {
    int id;
    printf("Enter verification ID: ");
    scanf("%d", &id);
    if (validateID(id))
        printf("Yes, please enter.\n");
}

void checkParcelID() {
    int id;
    printf("Enter parcel ID: ");
    scanf("%d", &id);
    if (validateID(id))
        printf("Yes, please enter.\n");
}

void checkTicketNumber() {
    int number;
    printf("Enter ticket number: ");
    scanf("%d", &number);
    if (validateID(number))
        printf("Yes, please enter.\n");
}

int readTime(int *hours, int *minutes, char *am_pm) {
    printf("Enter time (hh:mm AM/PM): ");
    if (scanf("%d:%d %2s", hours, minutes, am_pm) != 3)
        return 0;
    return validateTime(*hours, *minutes, am_pm);
}

void bookTicket() {
    Ticket newTicket;
    printf("Enter passenger name: ");
    scanf("%s", newTicket.name);
    printf("Enter destination: ");
    scanf("%s", newTicket.destination);

    if (!readTime(&newTicket.hours, &newTicket.minutes, newTicket.am_pm)) {
        printf("Invalid time format. Ticket booking failed.\n");
        return;
    }

    Node* newNode = (Node*)malloc(sizeof(Node));
    newNode->ticket = newTicket;
    newNode->next = NULL;

    if (head == NULL) {
        head = newNode;
    } else {
        Node* current = head;
        while (current->next != NULL)
            current = current->next;
        current->next = newNode;
    }

    printf("Ticket booked successfully.\n");
}

void displayBookedTickets() {
    if (head == NULL) {
        printf("No tickets booked yet.\n");
        return;
    }

    printf("Booked Tickets:\n");
    Node* current = head;
    int count = 1;
    while (current != NULL) {
        printf("Ticket %d:\n", count);
        printf("Passenger Name: %s\n", current->ticket.name);
        printf("Destination: %s\n", current->ticket.destination);
        printf("Time: %02d:%02d %s\n", current->ticket.hours, current->ticket.minutes, current->ticket.am_pm);
        printf("------------------------\n");
        current = current->next;
        count++;
    }
}

int main() {
    int choice;

    do {
        printf("Airport Entrance Management System\n");
        printf("1. Check Verification ID\n");
        printf("2. Check Parcel ID\n");
        printf("3. Check Ticket Number\n");
        printf("4. Book Ticket\n");
        printf("5. Display Booked Tickets\n");
        printf("6. Exit\n");
        printf("Enter your choice: ");
        scanf("%d", &choice);

        switch (choice) {
            case 1:
                checkVerificationID();
                break;
            case 2:
                checkParcelID();
                break;
            case 3:
                checkTicketNumber();
                break;
            case 4:
                bookTicket();
                break;
            case 5:
                displayBookedTickets();
                break;
            case 6:
                printf("Exiting...\n");
                break;
            default:
                printf("Invalid choice. Please try again.\n");
        }

        printf("\n");
    } while (choice != 6);

    return 0;
}
