package airport.entrance.management;

import java.util.List;
import java.util.Scanner;

public class AddNewID {
    public void execute(List<Person> persons) {
        Scanner scanner = new Scanner(System.in);
        System.out.print("Enter Name: ");
        String name = scanner.nextLine();
        System.out.print("Enter ID: ");
        int id = scanner.nextInt();
        System.out.println("Enter Contact Number");
        int num = scanner.nextInt();

        Person person = new Person(name, id, num);
        persons.add(person);
        System.out.println("ID added successfully!");
    }
}
